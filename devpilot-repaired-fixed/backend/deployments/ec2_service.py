"""Real EC2 deployment through AWS Systems Manager (SSM).
Requires an SSM-managed EC2 instance with Docker, unzip, AWS CLI, and an instance
profile permitted to read the deployment artifact bucket. No simulated success path.
"""
from __future__ import annotations
import io, os, re, shlex, subprocess, tempfile, time, zipfile
from pathlib import Path
from urllib.parse import urlparse
import boto3
from botocore.exceptions import BotoCoreError, ClientError

class DeploymentError(RuntimeError):
    pass


def _safe_name(value: str) -> str:
    name = re.sub(r'[^a-zA-Z0-9_.-]+', '-', value).strip('-.').lower()
    if not name:
        raise DeploymentError('Deployment name must contain letters or numbers.')
    return name[:50]


def _validate_repo(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    if parsed.scheme != 'https' or parsed.hostname not in {'github.com', 'www.github.com'}:
        raise DeploymentError('Provide an HTTPS GitHub repository URL. SSH URLs and other hosts are not supported.')
    if not parsed.path.strip('/').removesuffix('.git'):
        raise DeploymentError('GitHub repository URL is incomplete.')
    return repo_url


def _archive_source(repo_url: str, branch: str) -> bytes:
    _validate_repo(repo_url)
    if not re.fullmatch(r'[A-Za-z0-9._/-]{1,120}', branch) or '..' in branch.split('/'):
        raise DeploymentError('Invalid branch name.')
    with tempfile.TemporaryDirectory(prefix='devpilot-src-') as tmp:
        target=Path(tmp)/'source'
        cmd=['git','clone','--depth','1','--branch',branch,'--',repo_url,str(target)]
        try:
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=180,check=False)
        except FileNotFoundError as exc:
            raise DeploymentError('Git is not installed on the DevPilot backend host.') from exc
        if result.returncode:
            detail=(result.stderr or result.stdout or 'Git clone failed').strip()[-1500:]
            raise DeploymentError(f'Git checkout failed: {detail}')
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
            for p in target.rglob('*'):
                if not p.is_file(): continue
                rel=p.relative_to(target)
                if any(part in {'.git','node_modules','venv','.venv','__pycache__'} for part in rel.parts): continue
                if p.name in {'.env','.env.local','.env.production'}: continue
                z.write(p,rel.as_posix())
        return buf.getvalue()


def deploy_to_ec2(*, name: str, repo_url: str, branch: str, container_port: int,
                  host_port: int, timeout_seconds: int=600) -> dict:
    region=os.getenv('AWS_REGION','ap-south-1')
    instance_id=os.getenv('EC2_INSTANCE_ID','').strip()
    bucket=os.getenv('DEPLOYMENT_ARTIFACT_BUCKET','').strip()
    if not instance_id or not bucket:
        raise DeploymentError('AWS deployment is not configured. Set EC2_INSTANCE_ID and DEPLOYMENT_ARTIFACT_BUCKET.')
    if not re.fullmatch(r'i-[0-9a-fA-F]{8,17}',instance_id):
        raise DeploymentError('EC2_INSTANCE_ID is invalid.')
    if not (1 <= container_port <= 65535 and 1 <= host_port <= 65535):
        raise DeploymentError('Container and host ports must be between 1 and 65535.')
    image=_safe_name(name)
    artifact=f'devpilot-artifacts/{image}-{int(time.time())}.zip'
    try:
        session=boto3.Session(region_name=region)
        s3=session.client('s3'); ssm=session.client('ssm'); ec2=session.client('ec2')
        # Validate configured instance exists and is running before spending time cloning.
        info=ec2.describe_instances(InstanceIds=[instance_id])
        instances=[i for r in info.get('Reservations',[]) for i in r.get('Instances',[])]
        if not instances or instances[0].get('State',{}).get('Name')!='running':
            raise DeploymentError('Configured EC2 instance is not running.')
        source=_archive_source(repo_url,branch)
        s3.put_object(Bucket=bucket,Key=artifact,Body=source,ContentType='application/zip',ServerSideEncryption='AES256')
        script='\n'.join([
            'set -Eeuo pipefail',
            'command -v docker >/dev/null 2>&1 || { echo "Docker is not installed"; exit 20; }',
            'command -v aws >/dev/null 2>&1 || { echo "AWS CLI is not installed"; exit 21; }',
            'WORK=$(mktemp -d /tmp/devpilot.XXXXXX)',
            f'aws s3 cp {shlex.quote("s3://"+bucket+"/"+artifact)} "$WORK/source.zip" --region {shlex.quote(region)}',
            'unzip -q "$WORK/source.zip" -d "$WORK/app"',
            f'docker build -t {shlex.quote(image+":latest")} "$WORK/app"',
            f'docker rm -f {shlex.quote(image)} >/dev/null 2>&1 || true',
            f'docker run -d --restart unless-stopped --name {shlex.quote(image)} -p {host_port}:{container_port} {shlex.quote(image+":latest")}',
            f'docker inspect --format "{{{{.State.Running}}}}" {shlex.quote(image)} | grep -qx true',
            f'echo "DEVpilot_DEPLOYMENT_OK {image}"',
            'rm -rf "$WORK"',
        ])
        sent=ssm.send_command(InstanceIds=[instance_id],DocumentName='AWS-RunShellScript',
            Parameters={'commands':[script]},TimeoutSeconds=timeout_seconds,Comment=f'DevPilot deployment {image}')
        command_id=sent['Command']['CommandId']
        deadline=time.time()+timeout_seconds
        invocation=None
        while time.time()<deadline:
            try:
                invocation=ssm.get_command_invocation(CommandId=command_id,InstanceId=instance_id)
                if invocation.get('Status') in {'Success','Failed','Cancelled','TimedOut','Undeliverable','Terminated'}: break
            except ssm.exceptions.InvocationDoesNotExist:
                pass
            time.sleep(3)
        if not invocation or invocation.get('Status')!='Success':
            status=invocation.get('Status','NoInvocation') if invocation else 'TimedOut'
            stderr=(invocation.get('StandardErrorContent','') if invocation else '')[-3000:]
            stdout=(invocation.get('StandardOutputContent','') if invocation else '')[-1000:]
            raise DeploymentError(f'EC2 deployment did not complete successfully (SSM: {status}). {stderr or stdout}')
        return {'status':'SUCCESS','message':'EC2 accepted the deployment and Docker confirmed the container is running.',
                'instance_id':instance_id,'region':region,'artifact_key':artifact,'command_id':command_id,
                'container_name':image,'host_port':host_port,'container_port':container_port,
                'stdout':invocation.get('StandardOutputContent','')[-3000:]}
    except DeploymentError:
        raise
    except (BotoCoreError,ClientError,KeyError) as exc:
        raise DeploymentError(f'AWS deployment failed: {exc}') from exc
