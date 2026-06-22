# Build stage
FROM rust:1.96-slim as builder

WORKDIR /app

# Set target to Linux
ENV CARGO_TARGET=x86_64-unknown-linux-gnu

# Copy source
COPY . .

# Build the release binary for Linux
RUN cargo build --release --target x86_64-unknown-linux-gnu

# Runtime stage
FROM debian:bookworm-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/target/x86_64-unknown-linux-gnu/release/diam-db /app/diam-db

# Create data directory
RUN mkdir -p /data

# Expose port
EXPOSE 8080

# Set data directory
ENV DIAMDB_DATA_DIR=/data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/database/create || exit 1

# Run the server
CMD ["./diam-db", "server", "--host", "0.0.0.0", "--port", "8080", "--data-dir", "/data"]
