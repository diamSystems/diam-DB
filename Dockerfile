# Build stage
FROM rust:1.96-slim as builder

WORKDIR /app

# Copy source
COPY . .

# Build the release binary (native Linux target)
RUN cargo build --release

# Runtime stage
FROM debian:bookworm-slim

# Install dependencies (curl is required by the HEALTHCHECK below)
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/target/release/diam-db /app/diam-db

# Create data directory
RUN mkdir -p /data

# Expose port
EXPOSE 8080

# Set data directory
ENV DIAMDB_DATA_DIR=/data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the server
CMD ["./diam-db", "server", "--host", "0.0.0.0", "--port", "8080", "--data-dir", "/data"]
