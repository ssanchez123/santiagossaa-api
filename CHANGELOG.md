# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-03

### Added
- Initial FastAPI application with health and info endpoints
- Docker support with `docker-compose`
- CI pipeline with GitHub Actions (lint, type check, test, Docker build)
- Project structure with API versioning (`/api/v1/`)
- Pydantic Settings for configuration management
- Pre-commit hooks (ruff, mypy)
- Issue templates (bug report, feature request)
- MIT License