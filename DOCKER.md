# Docker Distribution for diam-DB

diam-DB is available as a Docker container for easy deployment across all platforms. This eliminates the need for platform-specific binaries and code signing certificates.

## Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine (Linux)
  - Download: https://www.docker.com/products/docker-desktop/
  - Free for personal use

## Quick Start

### Option 1: Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/diamsystems/diam-db.git
cd diam-db

# Start the container
docker-compose up -d

# diam-DB is now running on http://localhost:8080
```

### Option 2: Using Docker CLI

```bash
# Pull the image
docker pull ghcr.io/diamsystems/diam-db:latest

# Run the container
docker run -d --name diam-db -p 8080:8080 -v $(pwd)/data:/data ghcr.io/diamsystems/diam-db:latest

# diam-DB is now running on http://localhost:8080
```

### Option 3: Using CLI Wrapper Scripts

**Windows (PowerShell):**
```powershell
# Make the script executable (if needed)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Run commands
.\diam-db.ps1 server
.\diam-db.ps1 create-tenant my_tenant
```

**Linux/macOS (Bash):**
```bash
# Make the script executable
chmod +x diam-db.sh

# Run commands
./diam-db.sh server
./diam-db.sh create-tenant my_tenant
```

## Data Persistence

Data is persisted via Docker volumes. The container mounts `/data` to a host directory:

- **Docker Compose:** Automatically mounts `./data` in the project directory
- **Docker CLI:** Use `-v $(pwd)/data:/data` to mount a local directory
- **Windows PowerShell:** Use `-v "${PWD}/data:/data"`

## Configuration

Environment variables can be passed to the container:

```bash
docker run -d --name diam-db \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  -e DIAMDB_DATA_DIR=/data \
  ghcr.io/diamsystems/diam-db:latest
```

Available environment variables:
- `DIAMDB_DATA_DIR`: Data directory path (default: `/data`)

## API Access

Once running, diam-DB's HTTP API is available at `http://localhost:8080/api/v1`

### Example API Calls

```bash
# Create a tenant
curl -X POST http://localhost:8080/api/v1/database/create \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "my_tenant"}'

# Write a document
curl -X POST http://localhost:8080/api/v1/my_tenant/collection/users \
  -H "Content-Type: application/json" \
  -d '{"name": "John", "email": "john@example.com"}'

# Read a collection
curl http://localhost:8080/api/v1/my_tenant/collection/users
```

## Stopping the Container

```bash
# Stop the container
docker stop diam-db

# Remove the container
docker rm diam-db

# Or with docker-compose
docker-compose down
```

## Building Locally

```bash
# Build the image
docker build -t diam-db:local .

# Run the local build
docker run -d --name diam-db -p 8080:8080 -v $(pwd)/data:/data diam-db:local
```

## Health Check

The container includes a health check that monitors the API endpoint:

```bash
# Check container health
docker ps
# Look for "healthy" status under STATUS column

# Check health manually
curl http://localhost:8080/api/v1/database/create
```

## Troubleshooting

### Container won't start
- Ensure Docker Desktop is running
- Check port 8080 is not already in use: `netstat -ano | findstr :8080` (Windows) or `lsof -i :8080` (Linux/macOS)
- View container logs: `docker logs diam-db`

### Permission errors on data directory
- Ensure the host data directory has write permissions
- On Linux/macOS: `chmod 777 ./data`

### Windows-specific issues
- Ensure WSL2 is enabled in Docker Desktop settings
- If using PowerShell wrapper, ensure execution policy allows scripts: `Set-ExecutionPolicy RemoteSigned`

## Production Deployment

For production deployments:

1. **Use a reverse proxy** (nginx, traefik) for TLS termination
2. **Set resource limits**:
   ```bash
   docker run -d --name diam-db \
     --memory="512m" \
     --cpus="1.0" \
     -p 8080:8080 \
     -v $(pwd)/data:/data \
     ghcr.io/diamsystems/diam-db:latest
   ```
3. **Use specific version tags** instead of `latest` for reproducibility
4. **Configure backup strategy** for the data volume
5. **Monitor container health** via Docker health checks or external monitoring

## Image Tags

- `latest`: Latest stable release
- `vX.Y.Z`: Specific version (e.g., `v1.0.1`)

## Security Notes

- The container runs as a non-root user (`diamdb`)
- Only port 8080 is exposed
- No unnecessary packages are included in the image
- For production, consider using Docker secrets for sensitive data

## Support

For issues or questions:
- GitHub: https://github.com/diamsystems/diam-db/issues
- Documentation: https://github.com/diamsystems/diam-db
