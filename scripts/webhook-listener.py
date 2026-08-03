#!/usr/bin/env python3
"""
Webhook listener for GitHub push events.
Receives webhooks from GitHub, validates the payload, and triggers deploy.

Features:
- Webhook signature verification
- AI-powered diff analysis (via Ollama) before deploy
- Sensitive file change detection
- Automatic rollback on health check failure
- Rich alerts to OpenClaw mailbox for Pidge → Mac notification

Runs on port 9100 (localhost only). Caddy proxies the webhook endpoint.
"""

import hmac
import hashlib
import subprocess
import logging
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, status
import uvicorn

# --- Configuration ---
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
REPO_PATH = os.environ.get("REPO_PATH", str(Path.home() / "services" / "santiagossaa-api"))
DEPLOY_SCRIPT = os.environ.get("DEPLOY_SCRIPT", str(Path.home() / "services" / "santiagossaa-api" / "scripts" / "deploy.sh"))
MAILBOX_PATH = Path.home() / ".openclaw" / "mailbox"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "glm-5.2:cloud")
HEALTH_URL = "http://localhost:3000/health"
HEALTH_TIMEOUT = 10
HEALTH_RETRIES = 6
HEALTH_RETRY_DELAY = 2  # seconds

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


# --- Helpers ---

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


def get_diff(repo_path: str, before: str, after: str, max_lines: int = 200) -> str:
    """Get the actual diff between two commits, truncated."""
    try:
        result = subprocess.run(
            ["git", "diff", before, after, "--stat", "--patch"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            lines = result.stdout.splitlines()
            if len(lines) > max_lines:
                return "\n".join(lines[:max_lines]) + f"\n... (truncated, {len(lines)} total lines)"
            return result.stdout
    except Exception as e:
        logger.error(f"Failed to get diff: {e}")
    return ""


def check_sensitive_changes(changed_files: list[str]) -> tuple[bool, list[str]]:
    """Check if changed files include sensitive ones."""
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


def ai_analyze_diff(diff: str, changed_files: list[str], sensitive_files: list[str]) -> dict:
    """
    Use Ollama to analyze the diff before deploying.
    Returns assessment dict with: risk_level, should_deploy, concerns, summary.
    """
    if not diff:
        return {"risk_level": "none", "should_deploy": True, "concerns": [], "summary": "No changes to analyze."}

    prompt = f"""You are a deployment safety reviewer. Analyze this git diff and assess deployment risk.

Changed files: {', '.join(changed_files)}
Sensitive files changed: {', '.join(sensitive_files) if sensitive_files else 'none'}

Diff:
```
{diff}
```

Respond with ONLY a JSON object. No markdown fences. No extra text. Use this exact format:
{{"risk_level": "low|medium|high|critical", "should_deploy": true|false, "concerns": ["concern"], "summary": "one sentence"}}

Risk levels:
- low: normal app code changes
- medium: config or dependency changes
- high: security-sensitive files changed
- critical: Dockerfile/docker-compose/CI changed or structure broken

If no concerns, use empty list: []
Be concise. No false positives for normal code changes."""

    try:
        payload = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.1, "num_predict": 400}
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            raw_response = result.get("response", "").strip()

        # Strip markdown code fences if present
        if raw_response.startswith("```"):
            raw_response = raw_response.split("\n", 1)[-1] if "\n" in raw_response else raw_response[3:]
            if raw_response.endswith("```"):
                raw_response = raw_response[:-3]
            raw_response = raw_response.strip()

        # Try direct JSON parse first
        try:
            assessment = json.loads(raw_response)
        except json.JSONDecodeError:
            # Fallback: extract JSON object with regex
            import re
            json_match = re.search(r'\{[^{}]*"risk_level"[^{}]*\}', raw_response, re.DOTALL)
            if json_match:
                try:
                    assessment = json.loads(json_match.group())
                except json.JSONDecodeError:
                    # Last resort: extract individual fields
                    risk = re.search(r'"risk_level"\s*:\s*"(\w+)"', raw_response)
                    deploy = re.search(r'"should_deploy"\s*:\s*(true|false)', raw_response)
                    assessment = {
                        "risk_level": risk.group(1) if risk else "unknown",
                        "should_deploy": deploy.group(1) == "true" if deploy else True,
                        "concerns": ["AI returned malformed JSON, parsed with regex"],
                        "summary": "Partial parse from malformed AI response.",
                    }
            else:
                raise ValueError(f"Could not extract JSON from: {raw_response[:200]}")

        logger.info(f"AI assessment: risk={assessment.get('risk_level')}, deploy={assessment.get('should_deploy')}")
        return assessment

    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        return {
            "risk_level": "unknown",
            "should_deploy": True,  # fail open — deploy anyway if AI is down
            "concerns": [f"AI analysis failed: {e}"],
            "summary": "AI analysis unavailable, proceeding with deploy.",
        }


def get_current_commit(repo_path: str) -> str:
    """Get current HEAD commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def rollback(repo_path: str, commit_hash: str) -> bool:
    """Rollback to a previous commit."""
    logger.warning(f"Rolling back to {commit_hash[:8]}")
    try:
        result = subprocess.run(
            ["git", "reset", "--hard", commit_hash],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error(f"Git reset failed: {result.stderr}")
            return False

        # Rebuild with old code
        build = subprocess.run(
            ["docker", "compose", "up", "-d", "--build"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if build.returncode != 0:
            logger.error(f"Docker rebuild failed during rollback: {build.stderr}")
            return False

        logger.info("Rollback complete")
        return True
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        return False


def health_check() -> dict | None:
    """Perform health check with retries."""
    for i in range(HEALTH_RETRIES):
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=HEALTH_TIMEOUT) as resp:
                return json.loads(resp.read())
        except Exception:
            if i < HEALTH_RETRIES - 1:
                import time
                time.sleep(HEALTH_RETRY_DELAY)
    return None


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


# --- Webhook handler ---

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

    # Save current commit for potential rollback
    previous_commit = get_current_commit(REPO_PATH)
    logger.info(f"Current HEAD: {previous_commit[:8] if previous_commit else 'unknown'}")

    # Pull latest
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

    # Analyze changes
    changed_files = get_changed_files(REPO_PATH, before, after)
    logger.info(f"Changed files: {changed_files}")

    is_sensitive, sensitive_files = check_sensitive_changes(changed_files)

    # Get diff for AI analysis
    diff = get_diff(REPO_PATH, before, after)

    # AI analysis (Miguel's pre-deploy review)
    logger.info("Running AI pre-deploy analysis...")
    ai_assessment = ai_analyze_diff(diff, changed_files, sensitive_files)

    # If AI says critical, STOP and alert
    if ai_assessment.get("risk_level") == "critical" and not ai_assessment.get("should_deploy", True):
        logger.warning("AI assessment: CRITICAL — blocking deploy")
        alert_details = {
            "repo": repo_name,
            "pusher": pusher,
            "commits": commit_msgs,
            "changed_files": changed_files,
            "sensitive_files": sensitive_files,
            "ai_assessment": ai_assessment,
            "action": "DEPLOY BLOCKED by AI reviewer",
            "previous_commit": previous_commit,
        }
        write_alert_to_mailbox("deploy-blocked", alert_details)
        return {"status": "blocked", "details": alert_details}

    # Alert on sensitive changes (but proceed)
    if is_sensitive or ai_assessment.get("risk_level") in ("high", "medium"):
        logger.warning(f"Sensitive/high-risk changes detected: {sensitive_files}")
        write_alert_to_mailbox("sensitive-changes", {
            "repo": repo_name,
            "pusher": pusher,
            "commits": commit_msgs,
            "changed_files": changed_files,
            "sensitive_files": sensitive_files,
            "ai_assessment": ai_assessment,
            "warning": "Sensitive files modified. Deploying with caution.",
            "previous_commit": previous_commit,
        })

    # Deploy
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
        "ai_assessment": ai_assessment,
        "deploy_stdout": deploy_result.stdout[-2000:],
        "deploy_stderr": deploy_result.stderr[-2000:],
        "deploy_exit_code": deploy_result.returncode,
        "previous_commit": previous_commit,
    }

    if deploy_result.returncode != 0:
        logger.error(f"Deploy script failed: {deploy_result.stderr}")
        # Attempt rollback
        if previous_commit:
            logger.info("Attempting automatic rollback...")
            rollback_ok = rollback(REPO_PATH, previous_commit)
            deploy_output["rollback"] = "successful" if rollback_ok else "failed"
        else:
            deploy_output["rollback"] = "skipped (no previous commit)"

        write_alert_to_mailbox("deploy-failed", deploy_output)
        return {"status": "deploy_failed", "details": deploy_output}

    # Health check
    health = health_check()
    if health is None:
        logger.error("Health check failed after deploy")
        # Attempt rollback
        if previous_commit:
            logger.info("Health check failed — attempting automatic rollback...")
            rollback_ok = rollback(REPO_PATH, previous_commit)
            deploy_output["rollback"] = "successful" if rollback_ok else "failed"
        else:
            deploy_output["rollback"] = "skipped (no previous commit)"

        deploy_output["health_check_error"] = "Health check failed after retries"
        write_alert_to_mailbox("health-check-failed", deploy_output)
        return {"status": "health_check_failed", "details": deploy_output}

    logger.info(f"Deploy successful. Health: {health}")
    return {"status": "deployed", "health": health, "details": deploy_output}


ALERTS_SEEN_FILE = MAILBOX_PATH / ".alerts-seen"


def get_unread_alerts() -> list[dict]:
    """Return alert files that haven't been seen yet."""
    MAILBOX_PATH.mkdir(parents=True, exist_ok=True)
    seen = set()
    if ALERTS_SEEN_FILE.exists():
        seen = set(ALERTS_SEEN_FILE.read_text().splitlines())
    alerts = []
    new_seen = set()
    for f in sorted(MAILBOX_PATH.glob("miguel-deploy-*.md")):
        if f.name not in seen:
            alerts.append({
                "file": f.name,
                "content": f.read_text(),
            })
            new_seen.add(f.name)
    # Update seen file
    if new_seen:
        seen.update(new_seen)
        ALERTS_SEEN_FILE.write_text("\n".join(sorted(seen)))
    return alerts


@app.get("/health")
async def health():
    return {"status": "ok", "service": "webhook-listener"}


@app.get("/alerts")
async def alerts():
    """Return unread deploy alerts. Called by Mac cron via HTTPS."""
    unread = get_unread_alerts()
    if unread:
        logger.info(f"{len(unread)} unread alerts retrieved")
    return {"count": len(unread), "alerts": unread}


if __name__ == "__main__":
    port = int(os.environ.get("WEBHOOK_PORT", "9100"))
    logger.info(f"Starting webhook listener on port {port}")
    logger.info(f"Repo path: {REPO_PATH}")
    logger.info(f"Deploy script: {DEPLOY_SCRIPT}")
    logger.info(f"Ollama model: {OLLAMA_MODEL}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")