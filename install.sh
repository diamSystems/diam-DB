#!/bin/bash
# Installation script for diamDB

set -e

INSTALL_DIR="/usr/local/bin"
BINARY_NAME="diam-db"

# Detect platform
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux)
    if [ "$ARCH" = "x86_64" ]; then
      BINARY_URL="https://github.com/diamSystems/diam-DB/releases/latest/download/diam-db-linux-x86_64"
    else
      echo "Unsupported architecture: $ARCH"
      exit 1
    fi
    ;;
  Darwin)
    if [ "$ARCH" = "arm64" ]; then
      BINARY_URL="https://github.com/diamSystems/diam-DB/releases/latest/download/diam-db-macos-arm64"
    elif [ "$ARCH" = "x86_64" ]; then
      BINARY_URL="https://github.com/diamSystems/diam-DB/releases/latest/download/diam-db-macos-x86_64"
    else
      echo "Unsupported architecture: $ARCH"
      exit 1
    fi
    ;;
  *)
    echo "Unsupported OS: $OS"
    exit 1
    ;;
esac

echo "Downloading diamDB for $OS $ARCH..."

# Download binary
curl -L -o /tmp/$BINARY_NAME $BINARY_URL

# Make executable
chmod +x /tmp/$BINARY_NAME

# Install
sudo mv /tmp/$BINARY_NAME $INSTALL_DIR/$BINARY_NAME

echo "diamDB installed successfully to $INSTALL_DIR/$BINARY_NAME"
echo ""
echo "Usage:"
echo "  diam-db server                    # Start server (default: 127.0.0.1:8080)"
echo "  diam-db server --host 0.0.0.0 --port 3000"
echo "  diam-db create-tenant my_tenant   # Create a new tenant"
