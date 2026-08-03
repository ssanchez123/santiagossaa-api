# Santiago API 🚀

> Self-hosted FastAPI deployed on a home server with Docker, Cloudflare Tunnel, and automated git-push-to-deploy CI/CD.

[![CI](https://github.com/ssanchez123/santiagossaa-api/actions/workflows/ci.yml/badge.svg)](https://github.com/ssanchez123/santiagossaa-api/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)

A minimal, production-ready FastAPI application that runs on a self-hosted mini PC behind Cloudflare Tunnel — no exposed ports, no Cloud VPS, no monthly hosting costs.

## ✨ Features

- **Zero-cost hosting** — runs on a home server, tunneled via Cloudflare
- **Git-push-to-deploy** — push to `main`, server auto-deploys
- **Docker-first** — one command to build and run
- **API versioning** — structured `/api/v1/` endpoints
- **Health checks** — built-in Docker health monitoring
- **Security hardened** — non-root container, dropped capabilities, read-only rootfs
- **Type-safe** — Pydantic settings, mypy, ruff pre-commit hooks

## 🚀 Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- Python 3.12+ (for local development)

### Run with Docker (recommended)

```bash
git clone https://github.com/ssanchez123/santiagossaa-api.git
cd santiagossaa-api
docker compose up -d
```

The API will be available at `http://localhost:3000`.

### Run locally (development)

```bash
git clone https://github.com/ssanchez123/santiagossaa-api.git
cd santiagossaa-api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 3000
```

### Verify it's running

```bash
curl http://localhost:3000/health
# {"status":"healthy"}

curl http://localhost:3000/
# {"status":"ok","message":"Hello from m1cr0l1n0","timestamp":"...","version":"1.0.0"}
```

## 📚 API Documentation

FastAPI auto-generates interactive docs:

- **Swagger UI:** `http://localhost:3000/docs`
- **ReDoc:** `http://localhost:3000/redoc`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Root — server info and status |
| `GET` | `/health` | Health check (used by Docker) |
| `GET` | `/api/v1/health` | Versioned health check |
| `GET` | `/api/v1/info` | Request metadata for diagnostics |

## 🧪 Testing

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## 🔧 Development

### Code quality

```bash
# Install pre-commit hooks
pre-commit install

# Run manually
ruff check app/ tests/
mypy app/ --ignore-missing-imports
```

### Project structure

```
santiagossaa-api/
├── app/
│   ├── api/v1/endpoints/    # API routes (versioned)
│   ├── core/                # Config and settings
│   ├── models/              # Data models
│   └── main.py              # App entrypoint
├── tests/                   # Test suite
├── .github/                 # CI workflows + issue templates
├── Dockerfile               # Production container
├── docker-compose.yml       # Orchestration
└── pyproject.toml           # Python project config
```

## 🏗️ Architecture

```
Internet → Cloudflare Tunnel → Caddy (reverse proxy) → Docker (FastAPI :3000)
```

- **Cloudflare Tunnel** — outbound-only connection, no inbound ports needed
- **Caddy** — reverse proxy with security headers
- **Docker** — isolated container with resource limits and security hardening

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Commit with conventional commits (`feat:`, `fix:`, `docs:`)
4. Open a Pull Request

## 📄 License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for more information.

## ⭐ Show your support

If this project helped you or you found the architecture useful, give it a star! It helps others discover the project.

---

<p align="center">Built with FastAPI, Docker, and ☕ on a home server</p>