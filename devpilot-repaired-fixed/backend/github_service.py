"""GitHub repository discovery and cloning into DevPilot's persistent Docker-mounted workspace."""
from __future__ import annotations
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPOSITORY_ROOT = PROJECT_ROOT / "data" / "repositories"
REPO_ROOT = Path(os.getenv("DEVPILOT_REPOSITORY_ROOT", str(DEFAULT_REPOSITORY_ROOT))).resolve()
GITHUB_API = "https://api.github.com"

class GitHubIntegrationError(RuntimeError):
    pass

def _token() -> str:
    return os.getenv("GITHUB_TOKEN", "").strip()

def _request_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "DevPilot-Agentic-DevOps",
    }
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        if exc.code in (401, 403):
            raise GitHubIntegrationError(
                "GitHub rejected the credentials or rate-limited the request. Check GITHUB_TOKEN and its repository read permissions."
            ) from exc
        if exc.code == 404:
            raise GitHubIntegrationError("GitHub user or repository was not found, or it is not accessible to this token.") from exc
        raise GitHubIntegrationError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise GitHubIntegrationError(f"Could not reach GitHub: {exc}") from exc

def list_repositories(username: str) -> list[dict[str, Any]]:
    username = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", username):
        raise GitHubIntegrationError("Enter a valid GitHub username.")
    token = _token()
    if token:
        url = f"{GITHUB_API}/user/repos?per_page=100&sort=updated&visibility=all&affiliation=owner,collaborator,organization_member"
    else:
        url = f"{GITHUB_API}/users/{urllib.parse.quote(username)}/repos?per_page=100&type=owner&sort=updated"
    repos: list[dict[str, Any]] = []
    page = 1
    while page <= 10:  # GitHub API pagination; hard cap 1,000 repositories per request.
        data = _request_json(url + f"&page={page}" if "?" in url else url + f"?page={page}")
        if not isinstance(data, list):
            raise GitHubIntegrationError("Unexpected response from GitHub repository API.")
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    # If a token is supplied, only include repositories owned by the requested user
    # or explicitly accessible through the authenticated user's affiliations.
    return [{
        "id": r["id"],
        "name": r["name"],
        "full_name": r["full_name"],
        "private": bool(r.get("private")),
        "default_branch": r.get("default_branch") or "main",
        "html_url": r["html_url"],
        "clone_url": r["clone_url"],
        "updated_at": r.get("updated_at"),
        "description": r.get("description") or "",
    } for r in repos if r.get("clone_url") and r.get("full_name")]

def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    token = _token()
    if token:
        # Supply credentials through the child process environment, not the command line
        # or repository remote URL. The saved origin remains a clean https:// URL.
        import base64
        auth = base64.b64encode(("x-access-token:" + token).encode()).decode()
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.extraheader"
        env["GIT_CONFIG_VALUE_0"] = "AUTHORIZATION: basic " + auth
    return env

def _run_git(args: list[str], *, cwd: Path | None = None) -> str:
    try:
        p = subprocess.run(
            ["git", *args], cwd=str(cwd) if cwd else None, env=_git_env(),
            capture_output=True, text=True, timeout=900, check=False
        )
    except FileNotFoundError as exc:
        raise GitHubIntegrationError("Git is not installed on the DevPilot backend host/container.") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitHubIntegrationError("Git operation timed out. Check repository size and network connectivity.") from exc
    if p.returncode:
        detail = (p.stderr or p.stdout or "Git operation failed").strip()[-1200:]
        raise GitHubIntegrationError(detail)
    return p.stdout.strip()

def sync_repositories(username: str, selected: list[str] | None = None) -> dict[str, Any]:
    repos = list_repositories(username)
    selected_set = set(selected or [])
    if selected_set:
        unknown = selected_set - {r["full_name"] for r in repos}
        if unknown:
            raise GitHubIntegrationError("One or more selected repositories are not accessible from this GitHub account.")
        repos = [r for r in repos if r["full_name"] in selected_set]
    if not repos:
        return {"workspace": str(REPO_ROOT), "total": 0, "cloned": 0, "updated": 0, "failed": 0, "results": []}
    REPO_ROOT.mkdir(parents=True, exist_ok=True)
    results = []
    for repo in repos:
        # Derive destination only from validated GitHub owner/repository components.
        owner, name = repo["full_name"].split("/", 1)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            results.append({"full_name": repo["full_name"], "status": "failed", "message": "Unsafe repository path."})
            continue
        dest = (REPO_ROOT / owner / name).resolve()
        if REPO_ROOT not in dest.parents:
            results.append({"full_name": repo["full_name"], "status": "failed", "message": "Repository path escaped workspace."})
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if (dest / ".git").is_dir():
                _run_git(["fetch", "--prune", "origin"], cwd=dest)
                _run_git(["pull", "--ff-only", "origin", repo["default_branch"]], cwd=dest)
                status = "updated"
            elif dest.exists():
                raise GitHubIntegrationError("Destination exists but is not a Git repository; move it aside before syncing.")
            else:
                _run_git(["clone", "--depth", "1", "--branch", repo["default_branch"], "--", repo["clone_url"], str(dest)])
                status = "cloned"
            results.append({"full_name": repo["full_name"], "status": status, "path": str(dest), "default_branch": repo["default_branch"]})
        except GitHubIntegrationError as exc:
            results.append({"full_name": repo["full_name"], "status": "failed", "message": str(exc)})
    return {
        "workspace": str(REPO_ROOT),
        "total": len(repos),
        "cloned": sum(x["status"] == "cloned" for x in results),
        "updated": sum(x["status"] == "updated" for x in results),
        "failed": sum(x["status"] == "failed" for x in results),
        "results": results,
    }

def workspace_status() -> dict[str, Any]:
    REPO_ROOT.mkdir(parents=True, exist_ok=True)
    repositories = []
    for git_dir in REPO_ROOT.glob("*/*/.git"):
        path = git_dir.parent
        try:
            branch = _run_git(["branch", "--show-current"], cwd=path)
            remote = _run_git(["remote", "get-url", "origin"], cwd=path)
            repositories.append({"name": path.name, "owner": path.parent.name, "full_name": f"{path.parent.name}/{path.name}", "branch": branch, "remote": remote, "path": str(path)})
        except GitHubIntegrationError:
            continue
    return {"workspace": str(REPO_ROOT), "repository_count": len(repositories), "repositories": repositories}
