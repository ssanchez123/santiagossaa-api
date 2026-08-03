#!/usr/bin/env python3
"""
Webhook listener for GitHub push events.
Receives webhooks from GitHub, validates the payload, and triggers deploy.

Runs on port 9100 (localhost only). Caddy proxies the webhook endpoint.
"""

import hmac
import hashlib
import subprocess
import logging
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, status
import uvicorn

# --- Configuration ---
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
REPO_PATH = os.environ.get("REPO_PATH", str(Path.home() / "services" / "santiagossaa-api"))
DEPLOY_SCRIPT = os.environ.get("DEPLOY_SCRIPT", str(Path.home() / "services" / "deploy.sh"))
MAILBOX_PATH = Path.home() / ".openclaw" / "mailbox"
SENSITIVE_FILES = {
    "docker-compose.yml",
    "Dockerfile",
    ".dockerignore",
    ".gitignore",
    "requirements.txt",
    "pyproject.toml",
    ".pre-commit-config.yaml",
    ".github/workflows/ci.yml",
    "Caddyfile",
    "app/core/config.py",
}
PROTECTED_DIRS = {"app/core", "app/models", ".github", "docs"}

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
logger = logging.getLogger("webhook-listener")

app = FastAPI(title="Deploy Webhook", docs_url=None, redoc_url=None)


def verify_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    """Verify GitHub webhook signature."""
    if not secret:
        logger.warning("No WEBHOOK_SECRET set — skipping verification")
        return True
    if not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def get_changed_files(repo_path: str, before: str, after: str) -> list[str]:
    """Get list of changed files between two commits."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", before, after],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception as e:
        logger.error(f"Failed to get changed files: {e}")
    return []


def check_sensitive_changes(changed_files: list[str]) -> tuple[bool, list[str]]:
    """Check if changed files include sensitive ones.
    Returns (is_sensitive, list_of_sensitive_files).
    """
    sensitive = []
    for f in changed_files:
        if f in SENSITIVE_FILES:
            sensitive.append(f)
            continue
        for d in PROTECTED_DIRS:
            if f.startswith(d):
                sensitive.append(f)
                break
    return len(sensitive) > 0, sensitive


def write_alert_to_mailbox(alert_type: str, details: dict) -> None:
    """Write an alert file to the OpenClaw mailbox for Pidge to pick up."""
    MAILBOX_PATH.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    filename = f"miguel-deploy-{alert_type}-{timestamp}.md"
    filepath = MAILBOX_PATH / filename

    content = f"""# Miguel Deploy Alert — {alert_type.upper()}

**Time:** {datetime.now(timezone.utc).isoformat()}
**Alert Type:** {alert_type}

## Details

```json
{json.dumps(details, indent=2)}
```

---
*This alert was generated automatically by the webhook listener on m1cr0l1n0.*
"""
    filepath.write_text(content)
    logger.info(f"Alert written to mailbox: {filepath}")


@app.post("/webhook")
async def webhook(request: Request):
    """Handle GitHub push webhook."""
    payload_raw = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    event_type = request.headers.get("X-GitHub-Event", "")

    if event_type != "push":
        return {"status": "ignored", "reason": f"event:{event_type}"}

    # Verify signature
    if not verify_signature(payload_raw, signature, WEBHOOK_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    payload = json.loads(payload_raw)
    ref = payload.get("ref", "")
    repo_name = payload.get("repository", {}).get("full_name", "")

    # Only deploy on main branch
    if ref != "refs/heads/main":
        logger.info(f"Ignored push to {ref}")
        return {"status": "ignored", "reason": f"ref:{ref}"}

    before = payload.get("before", "")
    after = payload.get("after", "")
    pusher = payload.get("pusher", {}).get("name", "unknown")
    commits = payload.get("commits", [])
    commit_msgs = [c.get("message", "").split("\n")[0] for c in commits]

    logger.info(f"Push to main by {pusher} on {repo_name}")
    logger.info(f"Commits: {commit_msgs}")

    # Get changed files
    # First pull to get latest
    pull_result = subprocess.run(
        ["git", "pull", "origin", "main"],
        cwd=REPO_PATH,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if pull_result.returncode != 0:
        logger.error(f"git pull failed: {pull_result.stderr}")
        write_alert_to_mailbox("pull-failed", {
            "error": pull_result.stderr,
            "repo": repo_name,
            "pusher": pusher,
            "commits": commit_msgs,
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="git pull failed",
        )

    changed_files = get_changed_files(REPO_PATH, before, after)
    logger.info(f"Changed files: {changed_files}")

    # Check for sensitive changes
    is_sensitive, sensitive_files = check_sensitive_changes(changed_files)
    if is_sensitive:
        logger.warning(f"Sensitive files changed: {sensitive_files}")
        write_alert_to_mailbox("sensitive-changes", {
            "repo": repo_name,
            "pusher": pusher,
            "commits": commit_msgs,
            "changed_files": changed_files,
            "sensitive_files": sensitive_files,
            "warning": "Sensitive files were modified. Review before deploying.",
        })
        # Still proceed with deploy but alert

    # Run deploy script
    logger.info("Triggering deploy script...")
    deploy_result = subprocess.run(
        [DEPLOY_SCRIPT],
        capture_output=True,
        text=True,
        timeout=120,
    )

    deploy_output = {
        "repo": repo_name,
        "pusher": pusher,
        "commits": commit_msgs,
        "changed_files": changed_files,
        "sensitive_files": sensitive_files if is_sensitive else [],
        "deploy_stdout": deploy_result.stdout[-2000:],
        "deploy_stderr": deploy_result.stderr[-2000:],
        "deploy_exit_code": deploy_result.returncode,
    }

    if deploy_result.returncode != 0:
        logger.error(f"Deploy failed: {deploy_result.stderr}")
        write_alert_to_mailbox("deploy-failed", deploy_output)
        return {"status": "deploy_failed", "details": deploy_output}

    # Health check
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:3000/health", timeout=10) as resp:
            health = json.loads(resp.read())
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        deploy_output["health_check_error"] = str(e)
        write_alert_to_mailbox("health-check-failed", deploy_output)
        return {"status": "health_check_failed", "details": deploy_output}

    logger.info(f"Deploy successful. Health: {health}")
    return {"status": "deployed", "health": health, "details": deploy_output}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "webhook-listener"}


if __name__ == "__main__":
    port = int(os.environ.get("WEBHOOK_PORT", "9100"))
    logger.info(f"Starting webhook listener on port {port}")
    logger.info(f"Repo path: {REPO_PATH}")
    logger.info(f"Deploy script: {DEPLOY_SCRIPT}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")