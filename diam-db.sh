#!/usr/bin/env bash
# diam-DB CLI wrapper for Docker
# Usage: ./diam-db.sh <command> [args]
# Example: ./diam-db.sh server
# Example: ./diam-db.sh create-tenant my_tenant

set -e

CONTAINER_NAME="diam-db"
IMAGE_NAME="ghcr.io/diamsystems/diam-db:latest"

# Check if Docker is running
if ! docker version &> /dev/null; then
    echo "Error: Docker is not running or not installed. Please install Docker Desktop."
    exit 1
fi

# Check if container is running
if ! docker ps --filter "name=$CONTAINER_NAME" --format "{{.Names}}" | grep -q "^$CONTAINER_NAME$"; then
    echo "Container '$CONTAINER_NAME' is not running. Starting it..."
    
    # Check if image exists locally
    if ! docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "^$IMAGE_NAME$"; then
        echo "Pulling Docker image..."
        docker pull "$IMAGE_NAME"
    fi
    
    # Start container
    docker run -d --name "$CONTAINER_NAME" -p 8080:8080 -v "$(pwd)/data:/data" "$IMAGE_NAME"
    
    # Wait for container to be ready
    echo "Waiting for container to start..."
    sleep 3
fi

# Execute command in container
docker exec -it "$CONTAINER_NAME" diam-db "$@"
