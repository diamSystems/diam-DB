# diamDB

**diamDB** is an ultra-lean, high-concurrency, memory-first NoSQL micro-database designed explicitly to bypass traditional file locking issues (like `SQLITE_BUSY`). It is built in Rust using Tokio and Axum, making it incredibly fast with a sub-50MB RAM footprint—perfect for micro-VM environments like Fly.io.

## Key Features

- **Memory-First Architecture**: All reads happen entirely in RAM with zero disk I/O, providing microsecond latencies using lock-free concurrent pointers (`DashMap` + `Arc<RwLock<T>>`).
- **Append-Only Write Pipeline**: Writes are instantly queued through an asynchronous `tokio::sync::mpsc` channel and flushed to a tenant-specific `transactions.log`. The API responds instantly without waiting for disk sync.
- **Multi-Tenant Sharding**: Data is siloed cleanly into `Database-per-Tenant` folders to ensure absolute data isolation.
- **Auto-Compaction**: Background workers periodically compact the `transactions.log` into a compiled `data.json` state map without blocking your API traffic.

## Getting Started

### Prerequisites
- Rust and Cargo (version 1.70 or higher recommended)

### Build and Run

Clone the repository and run:
```bash
cargo run --release
```

The database will start on `127.0.0.1:8080` by default. Data is persisted in the `./data` folder in your project root.

---

## API Reference

### 1. Create a Tenant
Initialize a new database environment for a specific tenant.
- **Endpoint:** `POST /api/v1/database/create`
- **Body:** `{"tenant_id": "your_tenant_id"}`

### 2. Write a Document
Insert or update a document. If you do not provide an `id` field in the payload, diamDB will automatically generate a UUID for you.
- **Endpoint:** `POST /api/v1/:tenant_id/collection/:collection_name`
- **Body:** Any valid JSON object.

### 3. Read a Collection
Fetch all documents currently inside a collection.
- **Endpoint:** `GET /api/v1/:tenant_id/collection/:collection_name`

### 4. Read a Single Document
Fetch a single document from a collection instantly from the memory cache.
- **Endpoint:** `GET /api/v1/:tenant_id/collection/:collection_name/document/:id`

---

## Python / Flask Integration Guide

Because diamDB relies on simple HTTP JSON REST principles, it pairs exceptionally well with a Python application like Flask. 

### Setup

```bash
pip install flask requests
```

### Example `app.py`

```python
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

DIAMDB_URL = "http://127.0.0.1:8080/api/v1"

@app.route('/register_tenant', methods=['POST'])
def register_tenant():
    """Create a new tenant isolated database."""
    tenant_id = request.json.get('tenant_id')
    
    # Call diamDB to provision the tenant
    resp = requests.post(f"{DIAMDB_URL}/database/create", json={"tenant_id": tenant_id})
    return jsonify({"message": "Tenant registered", "diamdb_status": resp.status_code})


@app.route('/<tenant_id>/users', methods=['POST'])
def create_user(tenant_id):
    """Write a new user into the tenant's diamDB."""
    user_data = request.json
    
    # Fire the write. diamDB queues this to disk and responds instantly!
    resp = requests.post(
        f"{DIAMDB_URL}/{tenant_id}/collection/users", 
        json=user_data
    )
    return jsonify({"message": "User inserted into diamDB"}), resp.status_code


@app.route('/<tenant_id>/users', methods=['GET'])
def get_users(tenant_id):
    """Read all users for a given tenant."""
    resp = requests.get(f"{DIAMDB_URL}/{tenant_id}/collection/users")
    
    # Returns the JSON map directly from diamDB's memory cache
    return jsonify(resp.json()), resp.status_code


@app.route('/<tenant_id>/users/<user_id>', methods=['GET'])
def get_single_user(tenant_id, user_id):
    """Read a specific user by their UUID."""
    resp = requests.get(f"{DIAMDB_URL}/{tenant_id}/collection/users/document/{user_id}")
    
    if resp.status_code == 404:
        return jsonify({"error": "User not found"}), 404
        
    return jsonify(resp.json()), 200

if __name__ == '__main__':
    app.run(port=5000)
```

### Testing the Python App

1. **Start diamDB:** `cargo run`
2. **Start Flask:** `python app.py`
3. **Test with cURL:**

```bash
# 1. Register a tenant via Python
curl -X POST http://localhost:5000/register_tenant \
    -H "Content-Type: application/json" \
    -d '{"tenant_id": "company_abc"}'

# 2. Insert a user via Python
curl -X POST http://localhost:5000/company_abc/users \
    -H "Content-Type: application/json" \
    -d '{"name": "Sarah Connor", "role": "Resistance Leader"}'

# 3. Read the users list back
curl http://localhost:5000/company_abc/users
```
