import os, mimetypes, re
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Form, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session
from botocore.exceptions import BotoCoreError, ClientError
from .database import init_db, get_db
from .models import AgentAction, Deployment, Incident, StoredFile
from .schemas import AgentRequest, DeploymentCreate, CreateTextFile, CreateFolder, RenameRequest, IncidentAnalyzeRequest, ApprovalRequest, ApprovalDecision
from .agent import run_agent
from .services.storage_service import storage
from .deployments.ec2_service import deploy_to_ec2, DeploymentError
app=FastAPI(title='DevPilot Agentic DevOps Control Center',version='2.0.0')
origins=[x.strip() for x in os.getenv('CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(',') if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
@app.on_event('startup')
def startup():
    init_db()
    # Historical simulated successes must never continue to look verified.
    from .database import SessionLocal
    db=SessionLocal()
    try:
        db.query(Deployment).filter(Deployment.status=='SUCCESS',Deployment.repo_url=='').update({'status':'LEGACY_UNVERIFIED','progress':0,'message':'Historical record from simulated pipeline; not verified as a real deployment.'})
        db.commit()
    finally: db.close()
@app.get('/')
def root(): return {'name':app.title,'status':'online','api_version':app.version}
@app.get('/api/health')
def health():
    s3=storage.health()
    return {'status':'healthy' if s3.get('connected') else 'degraded','api':'healthy','storage':s3,'aws_deployment_configured':bool(os.getenv('EC2_INSTANCE_ID') and os.getenv('DEPLOYMENT_ARTIFACT_BUCKET'))}
@app.get('/api/aws/health')
def aws_health():
    # S3 storage health is independent of optional EC2 deployment configuration.
    s3_status = storage.health()
    deployment_configured = bool(os.getenv('EC2_INSTANCE_ID') and os.getenv('DEPLOYMENT_ARTIFACT_BUCKET'))
    result = {
        'configured': storage.mode == 's3',
        'connected': bool(s3_status.get('connected')),
        'storage_mode': storage.mode,
        's3': s3_status,
        'deployment_configured': deployment_configured,
    }
    if deployment_configured:
        try:
            import boto3
            region = os.getenv('AWS_REGION', 'ap-south-1')
            session = boto3.Session(region_name=region)
            identity = session.client('sts').get_caller_identity()
            ec2 = session.client('ec2')
            response = ec2.describe_instances(InstanceIds=[os.environ['EC2_INSTANCE_ID']])
            instances = [item for reservation in response.get('Reservations', []) for item in reservation.get('Instances', [])]
            bucket = os.getenv('DEPLOYMENT_ARTIFACT_BUCKET', '').strip()
            session.client('s3').head_bucket(Bucket=bucket)
            result.update({
                'deployment_connected': bool(instances and instances[0].get('State', {}).get('Name') == 'running'),
                'account': identity.get('Account'),
                'region': region,
                'instance_state': instances[0]['State']['Name'] if instances else 'not_found',
                'deployment_bucket_access': 'verified',
            })
        except Exception as exc:
            result['deployment_connected'] = False
            result['deployment_message'] = str(exc)
    else:
        result['deployment_message'] = 'EC2 deployment is not configured; S3 file storage can still work.'
    return result

@app.post('/api/agent')
def agent(req:AgentRequest,db:Session=Depends(get_db)): return run_agent(req.request,db)
@app.get('/api/agent-actions')
def agent_actions(db:Session=Depends(get_db)):
    rows=db.query(AgentAction).order_by(AgentAction.created_at.desc()).limit(50).all()
    return [{'id':a.id,'request':a.request,'intent':a.intent,'tool':a.tool,'status':a.status,'output':a.output,'created_at':a.created_at.isoformat()} for a in rows]

@app.get('/api/github/status')
def github_status():
    from .github_service import workspace_status
    from shutil import which
    status = workspace_status()
    status.update({
        'github_token_configured': bool(os.getenv('GITHUB_TOKEN')),
        'git_available': bool(which('git')),
        'workspace_persistence': 'Docker bind-mounted folder when started with docker compose; local project data folder otherwise',
    })
    return status

@app.get('/api/github/repos')
def github_repositories(username: str):
    from .github_service import list_repositories, GitHubIntegrationError
    try:
        repos = list_repositories(username)
        return {'username': username, 'count': len(repos), 'repositories': repos,
                'visibility': 'private and public (token permissions)' if os.getenv('GITHUB_TOKEN') else 'public repositories only; configure GITHUB_TOKEN for private repositories'}
    except GitHubIntegrationError as exc:
        raise HTTPException(400, str(exc))

@app.post('/api/github/sync')
def github_sync(payload: dict = Body(...)):
    from .github_service import sync_repositories, GitHubIntegrationError
    username = str(payload.get('username', '')).strip()
    selected = payload.get('repositories')
    if selected is not None and (not isinstance(selected, list) or not all(isinstance(x, str) for x in selected)):
        raise HTTPException(422, 'repositories must be a list of repository full names.')
    try:
        return sync_repositories(username, selected)
    except GitHubIntegrationError as exc:
        raise HTTPException(400, str(exc))

@app.get('/api/deployments')
def deployments(db:Session=Depends(get_db)):
    rows=db.query(Deployment).order_by(Deployment.created_at.desc()).all()
    return [{'id':x.id,'name':x.name,'repo_url':x.repo_url,'branch':x.branch,'status':x.status,'progress':x.progress,'message':x.message,'created_at':x.created_at.isoformat(),'command_id':x.command_id} for x in rows]
@app.post('/api/deployments')
def create_deployment(req:DeploymentCreate,db:Session=Depends(get_db)):
    if not os.getenv('EC2_INSTANCE_ID') or not os.getenv('DEPLOYMENT_ARTIFACT_BUCKET'):
        raise HTTPException(503,'AWS EC2 deployment is not configured. Configure EC2_INSTANCE_ID and DEPLOYMENT_ARTIFACT_BUCKET first.')
    d=Deployment(name=req.name,repo_url=str(req.repo_url),branch=req.branch,status='PENDING',progress=0,message='Queued for real EC2 deployment.')
    db.add(d); db.commit(); db.refresh(d)
    try:
        d.status='RUNNING'; d.progress=10; d.message='Validating AWS, checking out source and preparing artifact.'; db.commit()
        result=deploy_to_ec2(name=req.name,repo_url=str(req.repo_url),branch=req.branch,container_port=req.container_port,host_port=req.host_port)
        d.status='SUCCESS'; d.progress=100; d.message=result['message']; d.command_id=result['command_id']; d.artifact_key=result['artifact_key']; db.commit()
        return {'id':d.id,'status':d.status,'progress':d.progress,'message':d.message,'details':result}
    except DeploymentError as e:
        d.status='FAILED'; d.progress=0; d.message=str(e); db.commit()
        raise HTTPException(502,detail={'id':d.id,'status':'FAILED','message':str(e)})
    except Exception as e:
        d.status='FAILED'; d.progress=0; d.message=f'Unexpected deployment error: {e}'; db.commit()
        raise HTTPException(500,detail={'id':d.id,'status':'FAILED','message':d.message})
@app.get('/api/incidents')
def incidents(db:Session=Depends(get_db)):
    rows=db.query(Incident).order_by(Incident.created_at.desc()).limit(100).all()
    return [{'id':x.id,'title':x.title,'severity':x.severity,'status':x.status,'evidence':x.evidence,'probable_cause':x.probable_cause,'recommendation':x.recommendation,'created_at':x.created_at.isoformat()} for x in rows]
@app.post('/api/incidents/analyze')
def analyze_incident(req:IncidentAnalyzeRequest,db:Session=Depends(get_db)):
    logs=req.logs[-200000:]
    t=logs.lower()
    rules=[
      (('connection refused','connecterror','connectionerror'),'Service or dependency connection refused','The application could not establish a network connection to a dependency or listening service.','Verify the target service is running, confirm host/port and Docker port mapping, then check firewall rules.'),
      (('out of memory','oomkilled','memoryerror'),'Possible memory exhaustion','The log contains an out-of-memory or memory allocation failure.','Inspect process/container memory usage and recent workload changes. Increase limits only after confirming the resource bottleneck.'),
      (('permission denied','accessdenied','forbidden'),'Permission or access failure','The process was denied access to a file or resource.','Check the exact resource and grant only the minimum required permission; do not use broad administrator access.'),
      (('timeout','timed out','deadline exceeded'),'Request or dependency timeout','An operation exceeded its configured time limit.','Check service latency, upstream dependencies, network path and recent deployment changes.'),
      (('traceback','exception','fatal','error'),'Application exception detected','The supplied logs contain an exception/error marker; the exact root cause is not proven by this text alone.','Inspect the complete stack trace and the first causal error, then reproduce in a non-production environment.'),
    ]
    match=next((r for r in rules if any(k in t for k in r[0])),None)
    if match:
        title,cause,recommendation=match[1:]
        severity='high' if any(k in t for k in ['fatal','out of memory','oomkilled']) else 'medium'
    else:
        title='Unclassified log event'; cause='No supported signature matched the supplied log excerpt.'
        recommendation='Collect timestamped application, container and dependency logs plus health/metric evidence before assigning a root cause.'; severity='low'
    # Lightweight local retrieval over the bundled DevOps runbook snippets.
    from .agent import retrieve_runbook
    refs=retrieve_runbook(logs)
    evidence=logs[-4000:]
    row=Incident(title=req.title, severity=severity, status='OPEN', evidence=evidence, probable_cause=cause,
                 recommendation=recommendation + ((' Retrieved guidance: '+ '; '.join(x['title'] for x in refs)+'.') if refs else ''))
    db.add(row); db.commit(); db.refresh(row)
    return {'id':row.id,'title':row.title,'severity':row.severity,'status':row.status,'probable_cause':row.probable_cause,'recommendation':row.recommendation,'evidence':row.evidence,'retrieved_runbooks':refs,'analysis_type':'local rule-based; no external LLM configured'}

@app.get('/api/knowledge/search')
def knowledge_search(q:str):
    from .agent import RUNBOOKS
    t=q.lower()
    results=[]
    for key,title,guidance in RUNBOOKS:
        score=(2 if key in t else 0)+sum(1 for word in title.lower().split() if len(word)>3 and word in t)
        if score: results.append({'title':title,'guidance':guidance,'score':score})
    return {'query':q,'results':sorted(results,key=lambda x:x['score'],reverse=True)[:5],'source':'bundled local runbooks'}

@app.get('/api/approvals')
def list_approvals(db:Session=Depends(get_db)):
    rows=db.query(AgentAction).filter(AgentAction.status.in_(['pending_approval','approved','rejected'])).order_by(AgentAction.created_at.desc()).limit(100).all()
    return [{'id':x.id,'request':x.request,'tool':x.tool,'status':x.status,'output':x.output,'created_at':x.created_at.isoformat()} for x in rows]

@app.post('/api/approvals')
def request_approval(req:ApprovalRequest,db:Session=Depends(get_db)):
    # Approval requests are records only. This API never executes a privileged operation.
    row=AgentAction(request=req.request,intent='approval',tool=req.tool,status='pending_approval',output=req.reason or 'Awaiting human review.')
    db.add(row); db.commit(); db.refresh(row)
    return {'id':row.id,'status':row.status,'message':'Approval request recorded. No operation has been executed.'}

@app.patch('/api/approvals/{action_id}')
def decide_approval(action_id:int,req:ApprovalDecision,db:Session=Depends(get_db)):
    row=db.query(AgentAction).filter(AgentAction.id==action_id,AgentAction.status=='pending_approval').first()
    if not row: raise HTTPException(404,'Pending approval request not found.')
    row.status='approved' if req.decision=='approve' else 'rejected'
    row.output=(row.output+' | Human decision: '+req.decision+'. Execution remains a separate, explicitly gated step.')
    db.commit()
    return {'id':row.id,'status':row.status,'executed':False,'message':'Decision recorded; no command was run.'}

@app.get('/api/monitoring/status')
def monitoring_status():
    import platform, shutil, subprocess
    docker={'available':False,'status':'not_installed'}
    if shutil.which('docker'):
        try:
            p=subprocess.run(['docker','info','--format','{{.ServerVersion}}'],capture_output=True,text=True,timeout=5)
            docker={'available':p.returncode==0,'status':'online' if p.returncode==0 else 'daemon_unavailable','version':p.stdout.strip() if p.returncode==0 else (p.stderr or p.stdout).strip()[-500:]}
        except Exception as e: docker={'available':True,'status':'check_failed','detail':str(e)}
    return {'api':'online','host_platform':platform.platform(),'docker':docker,'metrics':'Host CPU/memory metrics are not configured; Prometheus/Grafana integration remains pending.'}

@app.get('/api/storage')
def storage_list(prefix:str=''):
    try:return {'mode':storage.mode,'items':storage.list(prefix)}
    except (ValueError,BotoCoreError,ClientError) as e: raise HTTPException(502,str(e))
@app.post('/api/storage/create-folder')
def create_folder(req:CreateFolder,db:Session=Depends(get_db)):
    try:key=storage.create_folder(req.key); db.merge(StoredFile(name=Path(key.rstrip('/')).name,object_key=key,content_type='folder',size=0,storage=storage.mode)); db.commit(); return {'success':True,'key':key,'storage':storage.mode}
    except HTTPException: db.rollback(); raise
    except Exception as e: db.rollback(); raise HTTPException(400,str(e))
@app.post('/api/storage/create-file')
def create_file(req:CreateTextFile,db:Session=Depends(get_db)):
    try:
        data=req.content.encode(); result=storage.put_bytes(req.key,data,'text/plain'); db.merge(StoredFile(name=Path(req.key).name,object_key=result['key'],content_type='text/plain',size=len(data),storage=storage.mode)); db.commit(); return {'success':True,**result}
    except HTTPException: db.rollback(); raise
    except Exception as e: db.rollback(); raise HTTPException(400,str(e))
@app.post('/api/storage/upload')
async def upload(files: list[UploadFile] = File(...), prefix: str = Form(''), db: Session = Depends(get_db)):
    max_bytes = int(os.getenv('MAX_UPLOAD_MB', '100')) * 1024 * 1024
    results = []
    saved_keys = []
    try:
        for file in files:
            filename = Path((file.filename or 'upload.bin').replace('\\\\', '/')).name
            if not filename or filename in {'.', '..'}:
                raise HTTPException(400, 'Invalid uploaded filename.')
            data = await file.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise HTTPException(413, f'{filename} exceeds the {max_bytes // (1024 * 1024)} MB upload limit.')
            clean_prefix = prefix.strip('/')
            key = f"{clean_prefix}/" if clean_prefix else ''
            key += filename
            result = storage.put_bytes(key, data, file.content_type)
            saved_keys.append(result['key'])
            results.append(result)
            db.merge(StoredFile(name=filename, object_key=result['key'], content_type=result['type'], size=result['size'], storage=storage.mode))
        db.commit()
        return {'success': True, 'message': f'{len(results)} file(s) uploaded successfully.', 'files': results, 'mode': storage.mode}
    except HTTPException:
        db.rollback()
        for key in saved_keys:
            try: storage.delete(key)
            except Exception: pass
        raise
    except Exception as exc:
        db.rollback()
        for key in saved_keys:
            try: storage.delete(key)
            except Exception: pass
        raise HTTPException(502, f'Storage upload failed: {exc}')


@app.post('/api/storage/upload-folder')
async def upload_folder(files: list[UploadFile] = File(...), paths: list[str] = Form(...), prefix: str = Form(''), db: Session = Depends(get_db)):
    if len(files) != len(paths):
        raise HTTPException(400, 'Each uploaded file must have a matching relative path.')
    max_bytes = int(os.getenv('MAX_UPLOAD_MB', '100')) * 1024 * 1024
    results = []
    saved_keys = []
    try:
        for file, relative_path in zip(files, paths):
            safe_path = relative_path.replace('\\\\', '/').lstrip('/')
            path_parts = Path(safe_path).parts
            if not safe_path or any(part in {'..', '.'} for part in path_parts):
                raise HTTPException(400, 'Invalid folder upload path.')
            clean_prefix = prefix.strip('/')
            key = f"{clean_prefix}/" if clean_prefix else ''
            key += safe_path
            data = await file.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise HTTPException(413, f'{safe_path} exceeds the {max_bytes // (1024 * 1024)} MB upload limit.')
            result = storage.put_bytes(key, data, file.content_type)
            saved_keys.append(result['key'])
            results.append(result)
            db.merge(StoredFile(name=Path(safe_path).name, object_key=result['key'], content_type=result['type'], size=result['size'], storage=storage.mode))
        db.commit()
        return {'success': True, 'message': f'{len(results)} file(s) uploaded successfully.', 'files': results, 'mode': storage.mode}
    except HTTPException:
        db.rollback()
        for key in saved_keys:
            try: storage.delete(key)
            except Exception: pass
        raise
    except Exception as exc:
        db.rollback()
        for key in saved_keys:
            try: storage.delete(key)
            except Exception: pass
        raise HTTPException(502, f'Folder upload failed: {exc}')


@app.get('/api/storage/download')
def download(key:str):
    try:data=storage.get_bytes(key)
    except Exception as e: raise HTTPException(404,str(e))
    return Response(content=data,media_type=mimetypes.guess_type(key)[0] or 'application/octet-stream',headers={'Content-Disposition':f'attachment; filename="{Path(key).name}"'})
@app.delete('/api/storage')
def delete(key:str,db:Session=Depends(get_db)):
    try:storage.delete(key); db.query(StoredFile).filter(StoredFile.object_key==key).delete(); db.commit(); return {'success':True,'storage':storage.mode}
    except HTTPException: db.rollback(); raise
    except Exception as e: db.rollback(); raise HTTPException(400,str(e))
@app.patch('/api/storage')
def rename(key:str,req:RenameRequest,db:Session=Depends(get_db)):
    try:new=storage.rename(key,req.new_key); row=db.query(StoredFile).filter(StoredFile.object_key==key).first()
    except Exception as e: raise HTTPException(400,str(e))
    if row: row.object_key=new; row.name=Path(new).name; db.commit()
    return {'success':True,'key':new}
@app.get('/api/storage/summary')
def storage_summary():
    try:
        items=storage.list(''); return {'mode':storage.mode,'connected':storage.health()['connected'],'objects':len(items),'bytes':sum(i['size'] for i in items if not i['is_folder'])}
    except Exception as e: raise HTTPException(502,str(e))
