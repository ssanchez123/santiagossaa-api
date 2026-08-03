#!/usr/bin/env bash
# Deploy script — pulls latest code, rebuilds Docker image, and restarts container.
# Called by the webhook listener or manually.
set -euo pipefail

REPO_DIR="${1:-$HOME/services/santiagossaa-api}"
LOG_FILE="$HOME/services/deploy.log"

log() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*" | tee -a "$LOG_FILE"
}

log "=== Deploy started ==="
log "Repo: $REPO_DIR"

cd "$REPO_DIR"

# Pull latest
log "Pulling latest code..."
git pull origin main 2>&1 | tee -a "$LOG_FILE"

# Rebuild and restart
log "Building and restarting Docker container..."
docker compose up -d --build 2>&1 | tee -a "$LOG_FILE"

# Wait for health check
log "Waiting for health check..."
for i in $(seq 1 12); do
    if curl -sf http://localhost:3000/health > /dev/null 2>&1; then
        log "Health check passed (attempt $i)"
        log "=== Deploy successful ==="
        exit 0
    fi
    sleep 2
done

log "ERROR: Health check failed after 24s"
log "=== Deploy failed ==="
exit 1