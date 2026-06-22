"""
End-to-end tests for the diamDB stack (engine + gateway).

These tests run against live services:
- Engine: http://127.0.0.1:8080
- Gateway: http://127.0.0.1:5000

Prerequisites:
1. diamDB engine running on :8080 (Docker or local)
2. Gateway running on :5000 (python app.py)
3. Databases clean (users.db, audit.db will be used/created)

Run: pytest test_e2e.py -v
"""

import os
import sys
import time
import json
import uuid
import requests
import pytest

# Configuration
ENGINE_URL = os.environ.get("DIAMDB_ENGINE_URL", "http://127.0.0.1:8080")
GATEWAY_URL = os.environ.get("DIAMDB_GATEWAY_URL", "http://127.0.0.1:5000/api/v1")
TEST_PASSWORD = "E2ETestPass123!"
TEST_COLLECTION = "e2e_collection"


def wait_for_service(url, timeout=10):
    """Wait for a service to become available."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code in (200, 404, 405):  # Acceptable responses
                return True
        except requests.RequestException:
            time.sleep(0.5)
    return False


class TestEngineHealth:
    """Test the diamDB engine's health endpoint and path traversal defense."""

    def test_engine_health_endpoint(self):
        """Engine /health returns 200 with version info."""
        resp = requests.get(f"{ENGINE_URL}/health", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "diam-db"
        assert "version" in data

    def test_engine_path_traversal_blocked(self):
        """Engine rejects path traversal in tenant_id."""
        resp = requests.post(
            f"{ENGINE_URL}/api/v1/database/create",
            json={"tenant_id": "../../etc"},
            timeout=5,
        )
        assert resp.status_code == 400
        assert "forbidden" in resp.text.lower() or "invalid" in resp.text.lower()

    def test_engine_path_traversal_collection_blocked(self):
        """Engine rejects path traversal in collection_name."""
        # First create a valid tenant
        requests.post(
            f"{ENGINE_URL}/api/v1/database/create",
            json={"tenant_id": "valid_tenant"},
            timeout=5,
        )
        # Try to read with malicious collection name
        resp = requests.get(
            f"{ENGINE_URL}/api/v1/valid_tenant/collection/..evil",
            timeout=5,
        )
        assert resp.status_code == 400

    def test_engine_valid_tenant_creation(self):
        """Engine accepts valid tenant creation."""
        resp = requests.post(
            f"{ENGINE_URL}/api/v1/database/create",
            json={"tenant_id": "e2e_valid_tenant"},
            timeout=5,
        )
        assert resp.status_code in (201, 409)  # 201 or already exists


class TestGatewayHealth:
    """Test the gateway's health check and connectivity to the engine."""

    def test_gateway_health_endpoint(self):
        """Gateway /health returns 200 and reports engine status."""
        resp = requests.get(f"{GATEWAY_URL}/health", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["version"] == "2.0.0"
        assert data["diamdb_engine"] in ("connected", "disconnected")


class TestAuthFlow:
    """Test the full authentication flow."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Register a test user before each test."""
        self.test_email = f"e2e-auth-{uuid.uuid4().hex[:8]}@diamsys.co.uk"
        self.test_tenant = f"e2e_tenant_{uuid.uuid4().hex[:8]}"

    def test_register(self):
        """User registration creates account and returns API key."""
        resp = requests.post(
            f"{GATEWAY_URL}/auth/register",
            json={"email": self.test_email, "password": TEST_PASSWORD},
            timeout=5,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "api_key" in data
        assert data["api_key"].startswith("ddb_")
        assert "warning" in data  # Should warn about showing API key once

    def test_register_duplicate_rejected(self):
        """Duplicate registration is rejected."""
        # First registration
        requests.post(
            f"{GATEWAY_URL}/auth/register",
            json={"email": self.test_email, "password": TEST_PASSWORD},
            timeout=5,
        )
        # Duplicate
        resp = requests.post(
            f"{GATEWAY_URL}/auth/register",
            json={"email": self.test_email, "password": TEST_PASSWORD},
            timeout=5,
        )
        assert resp.status_code == 409  # Conflict
        assert "already" in resp.json()["error"].lower() or "registered" in resp.json()["error"].lower()

    def test_login(self):
        """User login returns JWT access token."""
        # Register first
        requests.post(
            f"{GATEWAY_URL}/auth/register",
            json={"email": self.test_email, "password": TEST_PASSWORD},
            timeout=5,
        )
        # Login
        resp = requests.post(
            f"{GATEWAY_URL}/auth/login",
            json={"email": self.test_email, "password": TEST_PASSWORD},
            timeout=5,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_invalid_credentials(self):
        """Login with invalid credentials is rejected."""
        resp = requests.post(
            f"{GATEWAY_URL}/auth/login",
            json={"email": self.test_email, "password": "WrongPassword123!"},
            timeout=5,
        )
        assert resp.status_code == 401

    def test_refresh_token(self):
        """Refresh token rotation works."""
        # Register and login
        requests.post(
            f"{GATEWAY_URL}/auth/register",
            json={"email": self.test_email, "password": TEST_PASSWORD},
            timeout=5,
        )
        login_resp = requests.post(
            f"{GATEWAY_URL}/auth/login",
            json={"email": self.test_email, "password": TEST_PASSWORD},
            timeout=5,
        )
        refresh_token = login_resp.json()["refresh_token"]

        # Refresh
        resp = requests.post(
            f"{GATEWAY_URL}/auth/refresh",
            json={"refresh_token": refresh_token},
            timeout=5,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data  # New refresh token

    def test_revoke_token(self):
        """Token revocation works."""
        # Register and login
        requests.post(
            f"{GATEWAY_URL}/auth/register",
            json={"email": self.test_email, "password": TEST_PASSWORD},
            timeout=5,
        )
        login_resp = requests.post(
            f"{GATEWAY_URL}/auth/login",
            json={"email": self.test_email, "password": TEST_PASSWORD},
            timeout=5,
        )
        refresh_token = login_resp.json()["refresh_token"]
        access_token = login_resp.json()["access_token"]

        # Revoke (requires auth)
        resp = requests.post(
            f"{GATEWAY_URL}/auth/revoke",
            json={"refresh_token": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=5,
        )
        assert resp.status_code == 200

        # Refresh should now fail
        resp = requests.post(
            f"{GATEWAY_URL}/auth/refresh",
            json={"refresh_token": refresh_token},
            timeout=5,
        )
        assert resp.status_code == 401


class TestTenantOperations:
    """Test tenant creation and data operations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Register and login to get a token."""
        self.test_email = f"e2e-tenant-{uuid.uuid4().hex[:8]}@diamsys.co.uk"
        self.test_tenant = f"e2e_tenant_{uuid.uuid4().hex[:8]}"
        requests.post(
            f"{GATEWAY_URL}/auth/register",
            json={"email": self.test_email, "password": TEST_PASSWORD},
            timeout=5,
        )
        login_resp = requests.post(
            f"{GATEWAY_URL}/auth/login",
            json={"email": self.test_email, "password": TEST_PASSWORD},
            timeout=5,
        )
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_create_tenant(self):
        """Create a tenant via gateway."""
        resp = requests.post(
            f"{GATEWAY_URL}/tenants",
            json={"tenant_id": self.test_tenant},
            headers=self.headers,
            timeout=5,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "message" in data

    def test_write_document(self):
        """Write a document to a collection."""
        # Create tenant first
        requests.post(
            f"{GATEWAY_URL}/tenants",
            json={"tenant_id": self.test_tenant},
            headers=self.headers,
            timeout=5,
        )
        # Write document
        doc = {"name": "E2E Test", "value": 42}
        resp = requests.post(
            f"{GATEWAY_URL}/{self.test_tenant}/collection/{TEST_COLLECTION}",
            json=doc,
            headers=self.headers,
            timeout=5,
        )
        assert resp.status_code in (200, 201)

    def test_read_collection(self):
        """Read documents from a collection."""
        # Create tenant and write document
        requests.post(
            f"{GATEWAY_URL}/tenants",
            json={"tenant_id": self.test_tenant},
            headers=self.headers,
            timeout=5,
        )
        doc = {"name": "E2E Test", "value": 42}
        requests.post(
            f"{GATEWAY_URL}/{self.test_tenant}/collection/{TEST_COLLECTION}",
            json=doc,
            headers=self.headers,
            timeout=5,
        )
        # Read
        resp = requests.get(
            f"{GATEWAY_URL}/{self.test_tenant}/collection/{TEST_COLLECTION}",
            headers=self.headers,
            timeout=5,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0  # At least one document

    def test_tenant_stats(self):
        """Get tenant statistics."""
        # Create tenant and write document
        requests.post(
            f"{GATEWAY_URL}/tenants",
            json={"tenant_id": self.test_tenant},
            headers=self.headers,
            timeout=5,
        )
        requests.post(
            f"{GATEWAY_URL}/{self.test_tenant}/collection/{TEST_COLLECTION}",
            json={"test": "data"},
            headers=self.headers,
            timeout=5,
        )
        # Get stats
        resp = requests.get(
            f"{GATEWAY_URL}/{self.test_tenant}/stats",
            headers=self.headers,
            timeout=5,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "collections" in data
        assert "total_documents" in data

    def test_unauthorized_access_rejected(self):
        """Requests without auth are rejected."""
        resp = requests.get(
            f"{GATEWAY_URL}/{self.test_tenant}/collection/{TEST_COLLECTION}",
            timeout=5,
        )
        assert resp.status_code == 401


class TestSecurityHeaders:
    """Test that security headers are present."""

    def test_security_headers_on_health(self):
        """Gateway returns security headers."""
        resp = requests.get(f"{GATEWAY_URL}/../health", timeout=5)
        headers = resp.headers
        assert "X-Content-Type-Options" in headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert "X-Frame-Options" in headers
        assert headers["X-Frame-Options"] == "DENY"
        assert "X-Request-Id" in headers


class TestInputValidation:
    """Test input validation at the gateway level."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Register and login to get a token."""
        self.test_email = f"e2e-input-{uuid.uuid4().hex[:8]}@diamsys.co.uk"
        requests.post(
            f"{GATEWAY_URL}/auth/register",
            json={"email": self.test_email, "password": TEST_PASSWORD},
            timeout=5,
        )
        login_resp = requests.post(
            f"{GATEWAY_URL}/auth/login",
            json={"email": self.test_email, "password": TEST_PASSWORD},
            timeout=5,
        )
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_path_traversal_blocked_at_gateway(self):
        """Gateway blocks path traversal in tenant_id."""
        resp = requests.post(
            f"{GATEWAY_URL}/../../etc/collection/test",
            json={"test": "data"},
            headers=self.headers,
            timeout=5,
        )
        assert resp.status_code == 400

    def test_weak_password_rejected(self):
        """Weak password is rejected during registration."""
        resp = requests.post(
            f"{GATEWAY_URL}/auth/register",
            json={"email": f"weak-{uuid.uuid4().hex[:8]}@diamsys.co.uk", "password": "123"},
            timeout=5,
        )
        assert resp.status_code == 400


# Setup/teardown for the entire test session
@pytest.fixture(scope="session", autouse=True)
def verify_services():
    """Verify required services are running before tests."""
    if not wait_for_service(f"{ENGINE_URL}/health", timeout=15):
        pytest.fail(f"diamDB engine not available at {ENGINE_URL}/health")
    if not wait_for_service(f"{GATEWAY_URL}/../health", timeout=15):
        pytest.fail(f"Gateway not available at {GATEWAY_URL}/../health")
    yield
