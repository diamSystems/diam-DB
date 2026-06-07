#!/bin/bash
set -e

VERSION="1.0.1"
PACKAGE_NAME="diam-db"
ARCH="amd64"

# Build for Linux
echo "Building for Linux..."
cargo build --release --target x86_64-unknown-linux-gnu

# Create package structure
mkdir -p packaging/debian/usr/local/bin
mkdir -p packaging/debian/DEBIAN

# Copy binary
cp target/x86_64-unknown-linux-gnu/release/diam-db packaging/debian/usr/local/bin/

# Copy control file
cp packaging/debian/control packaging/debian/DEBIAN/

# Set permissions
chmod 755 packaging/debian/usr/local/bin/diam-db

# Build package
dpkg-deb --build packaging/debian ${PACKAGE_NAME}_${VERSION}_${ARCH}.deb

echo "DEB package created: ${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
