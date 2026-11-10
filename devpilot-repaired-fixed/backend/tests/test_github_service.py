from pathlib import Path
import pytest
from backend import github_service as gh


def test_rejects_invalid_github_username():
    with pytest.raises(gh.GitHubIntegrationError):
        gh.list_repositories("not a username!")


def test_workspace_path_is_under_project_data(monkeypatch, tmp_path):
    monkeypatch.setattr(gh, "REPO_ROOT", tmp_path / "repos")
    status = gh.workspace_status()
    assert status["repository_count"] == 0
    assert Path(status["workspace"]).exists()


def test_sync_rejects_unknown_selected_repository(monkeypatch):
    monkeypatch.setattr(gh, "list_repositories", lambda username: [{"full_name": "owner/known", "clone_url": "https://github.com/owner/known.git", "default_branch": "main"}])
    with pytest.raises(gh.GitHubIntegrationError):
        gh.sync_repositories("owner", ["owner/not-known"])
