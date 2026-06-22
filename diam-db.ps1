#!/usr/bin/env pwsh
<#
.SYNOPSIS
diam-DB CLI wrapper for Docker

.DESCRIPTION
This script wraps the diam-DB CLI commands to run inside a Docker container.
Usage: .\diam-db.ps1 <command> [args]

.EXAMPLE
.\diam-db.ps1 server
.\diam-db.ps1 create-tenant my_tenant
#>

param(
    [Parameter(Position = 0, Mandatory = $true)]
    [string]$Command,
    
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ContainerName = "diam-db"
$ImageName = "ghcr.io/diamsystems/diam-db:latest"

# Check if Docker is running
try {
    $null = docker version 2>&1
} catch {
    Write-Error "Docker is not running or not installed. Please install Docker Desktop."
    exit 1
}

# Check if container is running
$container = docker ps --filter "name=$ContainerName" --format "{{.Names}}" 2>$null

if (-not $container) {
    Write-Host "Container '$ContainerName' is not running. Starting it..." -ForegroundColor Yellow
    
    # Check if image exists locally
    $image = docker images --format "{{.Repository}}:{{.Tag}}" | Select-String $ImageName
    if (-not $image) {
        Write-Host "Pulling Docker image..." -ForegroundColor Yellow
        docker pull $ImageName
    }
    
    # Start container
    docker run -d --name $ContainerName -p 8080:8080 -v "${PWD}/data:/data" $ImageName
    
    # Wait for container to be ready
    Write-Host "Waiting for container to start..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
}

# Execute command in container
$cmdArgs = @("diam-db", $Command) + $Args
docker exec -it $ContainerName @cmdArgs
