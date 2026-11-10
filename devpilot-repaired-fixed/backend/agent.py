"""Local, auditable DevPilot tool router. No simulated success and no arbitrary shell execution."""
from datetime import datetime, timezone
import shutil, subprocess
from sqlalchemy.orm import Session
from .models import AgentAction, Incident
from .services.storage_service import storage

RUNBOOKS = [
    ("container", "Docker container troubleshooting", "Check Docker daemon availability, inspect container state and logs, then verify the configured application port."),
    ("database", "Database connectivity troubleshooting", "Verify database host, port, credentials and network access. Never print secrets into incident logs."),
    ("memory", "High memory usage", "Inspect process and container memory metrics, identify the largest consumer and scale or tune only after approval."),
    ("timeout", "Application timeout troubleshooting", "Check application health endpoint, upstream dependencies, network connectivity and recent deployment changes."),
    ("permission", "Permission and access errors", "Check the minimum required file, IAM or service permissions. Avoid granting broad administrator access."),
    ("connection refused", "Connection refused troubleshooting", "Confirm the service is running and listening on the expected interface and port; check firewall and port mapping."),
]

def detect_intent(text: str) -> str:
    t=text.lower()
    if any(x in t for x in ['upload','file','folder','storage','cloud']): return 'cloud_storage'
    if any(x in t for x in ['deploy','release','publish']): return 'deploy'
    if any(x in t for x in ['incident','error','failure','log','debug','troubleshoot']): return 'incident_analysis'
    if any(x in t for x in ['docker','container']): return 'docker_status'
    if any(x in t for x in ['test','tests']): return 'run_tests'
    if any(x in t for x in ['health','status','healthy','monitor']): return 'health_check'
    return 'general'

def retrieve_runbook(text: str):
    t=text.lower()
    hits=[{'title':title,'guidance':guidance} for key,title,guidance in RUNBOOKS if key in t]
    return hits[:3]

def run_agent(request: str, db: Session):
    intent=detect_intent(request)
    executed=False; tool='agent.router'; status='planned'; output=''
    if intent=='health_check':
        from . import main
        output=str(main.health())
        tool='health.check'; status='executed'; executed=True
        message='Live backend and configured storage health were checked.'
    elif intent=='cloud_storage':
        items=storage.list('')
        output=f"Storage mode: {storage.mode}. Found {len(items)} item(s)."
        tool='storage.list'; status='executed'; executed=True
        message=output
    elif intent=='docker_status':
        if not shutil.which('docker'):
            output='Docker CLI is not installed or is not on PATH.'; status='unavailable'
            message=output
        else:
            p=subprocess.run(['docker','info','--format','{{.ServerVersion}}'],capture_output=True,text=True,timeout=8)
            if p.returncode==0:
                output='Docker Engine version '+p.stdout.strip(); status='executed'; executed=True
                message='Docker daemon is reachable: '+output
            else:
                output=(p.stderr or p.stdout).strip()[-1200:]; status='failed'; message='Docker check failed: '+output
        tool='docker.status'
    elif intent=='incident_analysis':
        row=db.query(Incident).order_by(Incident.created_at.desc()).first()
        tool='incident.latest'
        if row:
            runbooks=retrieve_runbook(' '.join([row.title,row.evidence,row.probable_cause]))
            output=f"Incident #{row.id}: {row.title}. Severity: {row.severity}. Evidence: {row.evidence}. Probable cause: {row.probable_cause}. Recommendation: {row.recommendation}. Retrieved runbooks: {[x['title'] for x in runbooks]}"
            message=output; status='executed'; executed=True
        else:
            output='No incident has been recorded. Use the Analyze logs action to submit actual application logs.'
            message=output; status='executed'; executed=True
    elif intent=='deploy':
        tool='deployment.pipeline'; status='blocked'
        output='Cloud deployment is unavailable until AWS account verification and EC2/SSM/S3 configuration are complete. No deployment was attempted.'
        message=output
    elif intent=='run_tests':
        tool='test.runner'; status='planned'
        output='For safety, tests are not launched from natural-language requests. Run the documented pytest command from the project terminal.'
        message=output
    else:
        message='I classified your request but do not have a matching safe tool. Try health, Docker status, incident analysis, storage listing or deployment status.'
        output=message
    action=AgentAction(request=request,intent=intent,tool=tool,status=status,output=output)
    db.add(action); db.commit(); db.refresh(action)
    return {'message':message,'intent':intent,'tool':tool,'status':status,'executed':executed,'action_id':action.id,'timestamp':datetime.now(timezone.utc).isoformat()}
