#!/bin/bash
set -e

echo "Building diamDB for multiple platforms..."

# Create release directory
mkdir -p release

# Build for macOS (Apple Silicon)
echo "Building for macOS (aarch64-apple-darwin)..."
cargo build --release --target aarch64-apple-darwin
cp target/aarch64-apple-darwin/release/diam-db release/diam-db-macos-arm64

# Build for macOS (Intel)
echo "Building for macOS (x86_64-apple-darwin)..."
cargo build --release --target x86_64-apple-darwin
cp target/x86_64-apple-darwin/release/diam-db release/diam-db-macos-x86_64

# Build for Linux (x86_64)
echo "Building for Linux (x86_64-unknown-linux-gnu)..."
cargo build --release --target x86_64-unknown-linux-gnu
cp target/x86_64-unknown-linux-gnu/release/diam-db release/diam-db-linux-x86_64

# Build for Windows (x86_64)
echo "Building for Windows (x86_64-pc-windows-msvc)..."
cargo build --release --target x86_64-pc-windows-msvc
cp target/x86_64-pc-windows-msvc/release/diam-db.exe release/diam-db-windows-x86_64.exe

echo "Build complete! Binaries are in the 'release' directory."
ls -lh release/
