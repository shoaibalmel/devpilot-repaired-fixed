from backend.deployments.ec2_service import _safe_name, _validate_repo, DeploymentError
from backend.agent import detect_intent, retrieve_runbook
import pytest

def test_name_sanitized():
    assert _safe_name("My app!!") == "my-app"

def test_repo_requires_https_github():
    assert _validate_repo("https://github.com/example/app.git").endswith(".git")
    with pytest.raises(DeploymentError): _validate_repo("file:///etc/passwd")

def test_agent_routes_without_claiming_execution():
    assert detect_intent("deploy the latest version") == "deploy"


def test_runbook_retrieval_returns_relevant_guidance():
    results = retrieve_runbook("Docker container connection refused")
    titles = [item["title"] for item in results]
    assert "Docker container troubleshooting" in titles
    assert "Connection refused troubleshooting" in titles
