#!/usr/bin/env bash
# dev.sh — Run the API locally for development
# Usage: ./dev.sh [docker|local]
set -euo pipefail

MODE="${1:-local}"

if [ "$MODE" = "docker" ]; then
    echo "🐳 Starting API with Docker Compose (dev)..."
    if command -v docker-compose &> /dev/null; then
        DC=docker-compose
    else
        DC="docker compose"
    fi
    $DC -f docker-compose.dev.yml up -d --build
    echo ""
    echo "✅ API running at http://localhost:3000"
    echo "📄 Docs at http://localhost:3000/docs"
    echo ""
    echo "Logs:  $DC -f docker-compose.dev.yml logs -f"
    echo "Stop:  $DC -f docker-compose.dev.yml down"
    echo ""
    $DC -f docker-compose.dev.yml logs -f

elif [ "$MODE" = "local" ]; then
    echo "🐍 Starting API locally (venv)..."
    if [ ! -d ".venv" ]; then
        echo "📦 Creating virtual environment..."
        python3 -m venv .venv
        .venv/bin/pip install -r requirements-dev.txt
    fi
    .venv/bin/uvicorn app.main:app --reload --port 3000

else
    echo "Usage: ./dev.sh [docker|local]"
    echo "  docker — run with docker compose (docker-compose.dev.yml)"
    echo "  local — run with venv + uvicorn (default)"
    exit 1
fi