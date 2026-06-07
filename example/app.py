from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

DIAMDB_URL = "http://127.0.0.1:8080/api/v1"

@app.route('/')
def index():
    return jsonify({
        "status": "Flask app running",
        "message": "Use the endpoints to interact with diamDB!"
    })

@app.route('/register_tenant', methods=['POST'])
def register_tenant():
    """Create a new tenant isolated database."""
    tenant_id = request.json.get('tenant_id')
    
    if not tenant_id:
        return jsonify({"error": "tenant_id is required"}), 400

    try:
        # Call diamDB to provision the tenant
        resp = requests.post(f"{DIAMDB_URL}/database/create", json={"tenant_id": tenant_id})
        
        if resp.status_code == 201:
            return jsonify({"message": f"Tenant '{tenant_id}' registered successfully!"}), 201
        else:
            return jsonify({"error": "Failed to register tenant", "details": resp.text}), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to diamDB. Is the Rust server running?"}), 503

@app.route('/<tenant_id>/<collection_name>', methods=['POST'])
def create_document(tenant_id, collection_name):
    """Write a new document into the tenant's diamDB collection."""
    doc_data = request.json
    
    try:
        # Fire the write. diamDB queues this to disk and responds instantly!
        resp = requests.post(
            f"{DIAMDB_URL}/{tenant_id}/collection/{collection_name}", 
            json=doc_data
        )
        return jsonify({"message": f"Document inserted into '{collection_name}'"}), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to diamDB. Is the Rust server running?"}), 503

@app.route('/<tenant_id>/<collection_name>', methods=['GET'])
def get_collection(tenant_id, collection_name):
    """Read all documents for a given collection."""
    try:
        resp = requests.get(f"{DIAMDB_URL}/{tenant_id}/collection/{collection_name}")
        # Returns the JSON map directly from diamDB's memory cache
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to diamDB. Is the Rust server running?"}), 503

@app.route('/<tenant_id>/<collection_name>/<document_id>', methods=['GET'])
def get_single_document(tenant_id, collection_name, document_id):
    """Read a specific document by its UUID."""
    try:
        resp = requests.get(f"{DIAMDB_URL}/{tenant_id}/collection/{collection_name}/document/{document_id}")
        
        if resp.status_code == 404:
            return jsonify({"error": "Document not found"}), 404
            
        return jsonify(resp.json()), 200
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to diamDB. Is the Rust server running?"}), 503

if __name__ == '__main__':
    print("Starting Flask Example App. Make sure diamDB is running on port 8080!")
    app.run(port=5000, debug=True)
