# Changelog

## [1.0.2] - 2025-06-22

### Security
- **Engine**: Added path traversal validation in `api.rs` to prevent directory traversal attacks via tenant_id and collection_name parameters
- **Gateway**: Replaced wildcard CORS origins with configurable allowlist via `CORS_ORIGINS` environment variable
- **UI**: Added HTML escaping function to prevent XSS vulnerabilities when rendering API/user content
- **Gateway**: Added rate limiting disable support via `RATELIMIT_ENABLED` environment variable for testing

### Fixed
- **Dockerfile**: Added `curl` installation for HEALTHCHECK instruction
- **Engine**: Added `/health` endpoint for Docker health checks and gateway connectivity probes
- **Engine**: Fixed clap argument conflict (removed short `-h` flag from `--host` argument)
- **Gateway**: Updated health check to use engine's new `/health` endpoint

### Added
- **E2E Tests**: Created `test_e2e.py` for end-to-end testing against live services
- **Git Hygiene**: Added `example/.gitignore` to prevent committing database files and Python cache

### Changed
- **Gateway**: Added environment variable support for disabling rate limiting in test environments

## [1.0.1] - 2024-06-07

### Added
- Initial release
- Memory-first NoSQL micro-database
- Enterprise Security Gateway with JWT auth
- Multi-tenant RBAC
- Audit logging
