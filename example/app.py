"""
diamDB Enterprise Security Gateway (v2.0.0)
===========================================
A hardened Flask gateway that sits in front of the diamDB engine and provides:

- JWT + API Key authentication (PBKDF2-HMAC-SHA256, 100k iterations)
- Tenant-scoped authorization (complete data isolation)
- Input validation (path traversal, payload size, field count, schema)
- Rate limiting (auth endpoints)
- Security headers (HSTS, CSP, X-Frame-Options, etc.)
- Audit logging (SQLite)
- GDPR delete (tombstone pattern)
- Account lockout (brute-force protection)
- Token refresh rotation (single-use refresh tokens)

Run:  python app.py            (gateway on :5000, diamDB engine on :8080)
Test: pytest test_security.py -v
"""

import os
import re
import json
import time
import uuid
import hmac
import hashlib
import secrets
import sqlite3
from functools import wraps

import jwt as pyjwt
import requests
from flask import Flask, jsonify, request, g
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class Config:
    DIAMDB_URL = os.environ.get("DIAMDB_URL", "http://127.0.0.1:8080/api/v1")
    USERS_DB_PATH = os.environ.get("USERS_DB_PATH", "users.db")
    AUDIT_DB_PATH = os.environ.get("AUDIT_DB_PATH", "audit.db")
    JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production-" + "0" * 16)
    ACCESS_TTL = 3600            # access token lifetime (seconds)
    REFRESH_TTL = 60 * 60 * 24 * 7  # refresh token lifetime (seconds)
    PBKDF2_ITERATIONS = 100_000
    MAX_PAYLOAD_BYTES = 1024 * 1024  # 1 MB
    MAX_FIELDS = 100
    MAX_IDENTIFIER_LEN = 64
    LOCKOUT_THRESHOLD = 5
    LOCKOUT_SECONDS = 15 * 60
    VERSION = "2.0.0"
    # Comma-separated allowlist of browser origins permitted to call the API.
    # Never use a wildcard in production. Override via CORS_ORIGINS env var.
    CORS_ORIGINS = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_PAYLOAD_BYTES
CORS(app, resources={r"/*": {"origins": Config.CORS_ORIGINS}},
     allow_headers=["Content-Type", "Authorization", "X-API-Key"],
     methods=["GET", "POST", "DELETE", "OPTIONS"])

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["500 per minute"],
    storage_uri="memory://",
)

# Disable rate limiting for E2E tests (set RATELIMIT_ENABLED=false)
if os.environ.get("RATELIMIT_ENABLED", "true").lower() == "false":
    limiter.enabled = False


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _users_db():
    conn = sqlite3.connect(Config.USERS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _audit_db():
    conn = sqlite3.connect(Config.AUDIT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_databases():
    """Create all required tables (idempotent)."""
    db = _users_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id              TEXT PRIMARY KEY,
            email           TEXT UNIQUE NOT NULL,
            password_hash   TEXT NOT NULL,
            salt            TEXT NOT NULL,
            api_key_hash    TEXT NOT NULL,
            role            TEXT NOT NULL DEFAULT 'user',
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until    REAL NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tenant_access (
            user_id   TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            PRIMARY KEY (user_id, tenant_id)
        );
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            token      TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            used       INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """
    )
    db.commit()
    db.close()

    audit = _audit_db()
    audit.executescript(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            action     TEXT NOT NULL,
            user_id    TEXT,
            ip_address TEXT,
            details    TEXT,
            timestamp  TEXT NOT NULL
        );
        """
    )
    audit.commit()
    audit.close()


def _audit(action, details="", user_id=None):
    try:
        db = _audit_db()
        db.execute(
            "INSERT INTO audit_log (action, user_id, ip_address, details, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (action, user_id, request.remote_addr if request else None,
             details, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        )
        db.commit()
        db.close()
    except Exception:
        # Auditing must never crash the request path.
        pass


# ---------------------------------------------------------------------------
# Security utility functions
# ---------------------------------------------------------------------------

def _hash_password(password, salt=None):
    """PBKDF2-HMAC-SHA256. Returns (hex_hash, salt)."""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), Config.PBKDF2_ITERATIONS
    )
    return dk.hex(), salt


def _verify_password(password, password_hash, salt):
    calc, _ = _hash_password(password, salt)
    return hmac.compare_digest(calc, password_hash)


def _generate_api_key():
    return "ddb_" + secrets.token_urlsafe(40)


def _hash_api_key(api_key):
    return hashlib.sha256(api_key.encode()).hexdigest()


def _validate_identifier(value, name):
    """Validate a tenant/collection identifier. Returns (valid, error)."""
    if not value or not isinstance(value, str):
        return False, f"{name} is required"
    if "\x00" in value:
        return False, f"{name} contains forbidden characters"
    if ".." in value or "/" in value or "\\" in value:
        return False, f"{name} contains forbidden characters"
    if len(value) > Config.MAX_IDENTIFIER_LEN:
        return False, f"{name} must be at most {Config.MAX_IDENTIFIER_LEN} characters"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return False, f"{name} contains invalid characters"
    return True, None


def _validate_email(email):
    if not email or not isinstance(email, str):
        return False, "Invalid email address"
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return False, "Invalid email address"
    return True, None


def _validate_password(password):
    if not isinstance(password, str) or len(password) < 12:
        return False, "Password must be at least 12 characters"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain an uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain a lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain a digit"
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Password must contain a special character"
    return True, None


def _validate_payload(payload):
    if not isinstance(payload, dict):
        return False, "Payload must be a JSON object"
    if len(payload) > Config.MAX_FIELDS:
        return False, f"Too many fields (max {Config.MAX_FIELDS})"
    if len(json.dumps(payload).encode()) > Config.MAX_PAYLOAD_BYTES:
        return False, "Payload too large"
    return True, None


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _make_access_token(user):
    now = int(time.time())
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role": user["role"],
        "iat": now,
        "exp": now + Config.ACCESS_TTL,
    }
    return pyjwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")


def _issue_refresh_token(user_id):
    token = secrets.token_urlsafe(48)
    db = _users_db()
    db.execute(
        "INSERT INTO refresh_tokens (token, user_id, used, created_at) VALUES (?, ?, 0, ?)",
        (token, user_id, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
    )
    db.commit()
    db.close()
    return token


def _get_user_by_id(user_id):
    db = _users_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    db.close()
    return dict(row) if row else None


def _get_user_by_email(email):
    db = _users_db()
    row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    db.close()
    return dict(row) if row else None


def _get_user_by_api_key(api_key):
    db = _users_db()
    row = db.execute(
        "SELECT * FROM users WHERE api_key_hash = ?", (_hash_api_key(api_key),)
    ).fetchone()
    db.close()
    return dict(row) if row else None


def _is_locked(user):
    return float(user.get("locked_until", 0) or 0) > time.time()


# ---------------------------------------------------------------------------
# Authentication / authorization
# ---------------------------------------------------------------------------

def _authenticate():
    """Resolve the caller. Returns (user_dict, error_tuple)."""
    auth_header = request.headers.get("Authorization", "")
    api_key = request.headers.get("X-API-Key")

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = pyjwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
        except pyjwt.ExpiredSignatureError:
            _audit("AUTH_FAILED", "Token expired")
            return None, (jsonify({"error": "Token expired"}), 401)
        except pyjwt.InvalidTokenError:
            _audit("AUTH_FAILED", "Invalid token")
            return None, (jsonify({"error": "Invalid token"}), 401)
        user = _get_user_by_id(payload.get("sub"))
        if not user:
            _audit("AUTH_FAILED", "Unknown subject")
            return None, (jsonify({"error": "Invalid token"}), 401)
        return user, None

    if api_key:
        user = _get_user_by_api_key(api_key)
        if not user:
            _audit("AUTH_FAILED", "Invalid API key")
            return None, (jsonify({"error": "Invalid API key"}), 401)
        return user, None

    _audit("AUTH_FAILED", "No credentials provided")
    return None, (jsonify({"error": "Authentication required"}), 401)


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user, err = _authenticate()
        if err:
            resp, code = err
            return resp, code
        if _is_locked(user):
            _audit("AUTH_BLOCKED", "Account locked", user_id=user["id"])
            return jsonify({"error": "Account locked due to too many failed attempts"}), 423
        g.user = user
        return f(*args, **kwargs)
    return wrapper


def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if g.user.get("role") != "admin":
            return jsonify({"error": "Admin privileges required"}), 403
        return f(*args, **kwargs)
    return wrapper


def _has_tenant_access(user, tenant_id):
    if user.get("role") == "admin":
        return True
    db = _users_db()
    row = db.execute(
        "SELECT 1 FROM tenant_access WHERE user_id = ? AND tenant_id = ?",
        (user["id"], tenant_id),
    ).fetchone()
    db.close()
    return row is not None


def _grant_tenant_access(user_id, tenant_id):
    db = _users_db()
    db.execute(
        "INSERT OR IGNORE INTO tenant_access (user_id, tenant_id) VALUES (?, ?)",
        (user_id, tenant_id),
    )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Response hardening
# ---------------------------------------------------------------------------

@app.after_request
def _security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-Id"] = uuid.uuid4().hex
    response.headers["Server"] = "diamDB-Gateway"
    return response


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return jsonify({
        "service": "diamDB Enterprise Security Gateway",
        "version": Config.VERSION,
        "security": {
            "authentication": "JWT + API Key",
            "authorization": "Tenant-scoped RBAC",
            "rate_limiting": "Enabled",
            "audit_logging": "Enabled",
        },
    }), 200


@app.route("/api/v1/health")
def health():
    engine = "disconnected"
    try:
        resp = requests.get(f"{Config.DIAMDB_URL}/health", timeout=2)
        if resp.status_code == 200:
            engine = "connected"
    except requests.exceptions.RequestException:
        engine = "disconnected"
    return jsonify({
        "status": "healthy",
        "version": Config.VERSION,
        "diamdb_engine": engine,
    }), 200


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.route("/api/v1/auth/register", methods=["POST"])
@limiter.limit("10 per minute")
def register():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")

    valid, err = _validate_email(email)
    if not valid:
        return jsonify({"error": err}), 400
    valid, err = _validate_password(password)
    if not valid:
        return jsonify({"error": err}), 400

    if _get_user_by_email(email):
        return jsonify({"error": "Email already registered"}), 409

    user_id = uuid.uuid4().hex
    pw_hash, salt = _hash_password(password)
    api_key = _generate_api_key()

    db = _users_db()
    db.execute(
        "INSERT INTO users (id, email, password_hash, salt, api_key_hash, role, "
        "failed_attempts, locked_until, created_at) VALUES (?, ?, ?, ?, ?, 'user', 0, 0, ?)",
        (user_id, email, pw_hash, salt, _hash_api_key(api_key),
         time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
    )
    db.commit()
    db.close()

    _audit("USER_REGISTERED", f"email={email}", user_id=user_id)
    return jsonify({
        "user_id": user_id,
        "api_key": api_key,
        "warning": "Store this API key securely. It will not be shown again.",
    }), 201


@app.route("/api/v1/auth/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")
    generic = "Invalid credentials"

    user = _get_user_by_email(email)
    if not user:
        _audit("AUTH_FAILED", f"Unknown email login attempt: {email}")
        return jsonify({"error": generic}), 401

    if _is_locked(user):
        _audit("AUTH_BLOCKED", "Login on locked account", user_id=user["id"])
        return jsonify({"error": "Account locked due to too many failed attempts"}), 423

    if not _verify_password(password or "", user["password_hash"], user["salt"]):
        attempts = user["failed_attempts"] + 1
        locked_until = 0
        if attempts >= Config.LOCKOUT_THRESHOLD:
            locked_until = time.time() + Config.LOCKOUT_SECONDS
        db = _users_db()
        db.execute(
            "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
            (attempts, locked_until, user["id"]),
        )
        db.commit()
        db.close()
        _audit("AUTH_FAILED", "Bad password", user_id=user["id"])
        return jsonify({"error": generic}), 401

    # Success — reset lockout counters.
    db = _users_db()
    db.execute(
        "UPDATE users SET failed_attempts = 0, locked_until = 0 WHERE id = ?",
        (user["id"],),
    )
    db.commit()
    db.close()

    access = _make_access_token(user)
    refresh = _issue_refresh_token(user["id"])
    _audit("LOGIN_SUCCESS", f"email={email}", user_id=user["id"])
    return jsonify({
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": Config.ACCESS_TTL,
    }), 200


@app.route("/api/v1/auth/refresh", methods=["POST"])
@limiter.limit("20 per minute")
def refresh():
    data = request.get_json(silent=True) or {}
    token = data.get("refresh_token")
    if not token:
        return jsonify({"error": "refresh_token is required"}), 401

    db = _users_db()
    row = db.execute(
        "SELECT * FROM refresh_tokens WHERE token = ? AND used = 0", (token,)
    ).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Invalid or expired refresh token"}), 401

    # Rotation: mark the old token used immediately.
    db.execute("UPDATE refresh_tokens SET used = 1 WHERE token = ?", (token,))
    db.commit()
    user_id = row["user_id"]
    db.close()

    user = _get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "Invalid refresh token"}), 401

    access = _make_access_token(user)
    new_refresh = _issue_refresh_token(user_id)
    return jsonify({
        "access_token": access,
        "refresh_token": new_refresh,
        "token_type": "Bearer",
        "expires_in": Config.ACCESS_TTL,
    }), 200


@app.route("/api/v1/auth/revoke", methods=["POST"])
@require_auth
def revoke():
    db = _users_db()
    db.execute("DELETE FROM refresh_tokens WHERE user_id = ?", (g.user["id"],))
    db.commit()
    db.close()
    _audit("TOKENS_REVOKED", "All refresh tokens revoked", user_id=g.user["id"])
    return jsonify({"message": "All tokens revoked"}), 200


# ---------------------------------------------------------------------------
# Tenant management
# ---------------------------------------------------------------------------

@app.route("/api/v1/tenants", methods=["POST"])
@require_auth
def create_tenant():
    data = request.get_json(silent=True) or {}
    tenant_id = data.get("tenant_id")

    valid, err = _validate_identifier(tenant_id, "tenant_id")
    if not valid:
        return jsonify({"error": err}), 400

    try:
        resp = requests.post(
            f"{Config.DIAMDB_URL}/database/create",
            json={"tenant_id": tenant_id}, timeout=10,
        )
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "diamDB engine unavailable"}), 503

    if resp.status_code in (200, 201):
        _grant_tenant_access(g.user["id"], tenant_id)
        _audit("TENANT_CREATED", f"tenant={tenant_id}", user_id=g.user["id"])
        return jsonify({"message": f"Tenant '{tenant_id}' created successfully"}), 201

    return jsonify({"error": "Failed to create tenant", "details": resp.text}), resp.status_code


# ---------------------------------------------------------------------------
# Collection / document operations (tenant-scoped)
# ---------------------------------------------------------------------------

@app.route("/api/v1/<tenant_id>/collection/<collection_name>", methods=["POST"])
@require_auth
def write_document(tenant_id, collection_name):
    valid, err = _validate_identifier(tenant_id, "tenant_id")
    if not valid:
        return jsonify({"error": err}), 400
    if not _has_tenant_access(g.user, tenant_id):
        return jsonify({"error": "Access to this tenant is forbidden"}), 403
    valid, err = _validate_identifier(collection_name, "collection_name")
    if not valid:
        return jsonify({"error": err}), 400

    data = request.get_json(silent=True) or {}
    valid, err = _validate_payload(data)
    if not valid:
        return jsonify({"error": err}), 400

    try:
        resp = requests.post(
            f"{Config.DIAMDB_URL}/{tenant_id}/collection/{collection_name}",
            json=data, timeout=10,
        )
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "diamDB engine unavailable"}), 503

    _audit("DOC_WRITE", f"tenant={tenant_id} collection={collection_name}", user_id=g.user["id"])
    body = {"message": f"Document written to '{collection_name}'"}
    try:
        parsed = resp.json()
        if isinstance(parsed, (dict, list)):
            body = parsed
    except (ValueError, TypeError):
        pass
    return jsonify(body), resp.status_code


@app.route("/api/v1/<tenant_id>/collection/<collection_name>", methods=["GET"])
@require_auth
def read_collection(tenant_id, collection_name):
    valid, err = _validate_identifier(tenant_id, "tenant_id")
    if not valid:
        return jsonify({"error": err}), 400
    if not _has_tenant_access(g.user, tenant_id):
        return jsonify({"error": "Access to this tenant is forbidden"}), 403
    valid, err = _validate_identifier(collection_name, "collection_name")
    if not valid:
        return jsonify({"error": err}), 400

    try:
        resp = requests.get(
            f"{Config.DIAMDB_URL}/{tenant_id}/collection/{collection_name}", timeout=10,
        )
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "diamDB engine unavailable"}), 503

    try:
        return jsonify(resp.json()), resp.status_code
    except ValueError:
        return jsonify({"data": resp.text}), resp.status_code


@app.route("/api/v1/<tenant_id>/collection/<collection_name>/document/<document_id>", methods=["GET"])
@require_auth
def read_document(tenant_id, collection_name, document_id):
    valid, err = _validate_identifier(tenant_id, "tenant_id")
    if not valid:
        return jsonify({"error": err}), 400
    if not _has_tenant_access(g.user, tenant_id):
        return jsonify({"error": "Access to this tenant is forbidden"}), 403
    valid, err = _validate_identifier(collection_name, "collection_name")
    if not valid:
        return jsonify({"error": err}), 400

    try:
        resp = requests.get(
            f"{Config.DIAMDB_URL}/{tenant_id}/collection/{collection_name}/document/{document_id}",
            timeout=10,
        )
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "diamDB engine unavailable"}), 503

    if resp.status_code == 404:
        return jsonify({"error": "Document not found"}), 404
    try:
        return jsonify(resp.json()), resp.status_code
    except ValueError:
        return jsonify({"data": resp.text}), resp.status_code


@app.route("/api/v1/<tenant_id>/collection/<collection_name>/document/<document_id>", methods=["DELETE"])
@require_auth
def delete_document(tenant_id, collection_name, document_id):
    """GDPR delete via tombstone (diamDB has no native delete)."""
    valid, err = _validate_identifier(tenant_id, "tenant_id")
    if not valid:
        return jsonify({"error": err}), 400
    if not _has_tenant_access(g.user, tenant_id):
        return jsonify({"error": "Access to this tenant is forbidden"}), 403

    tombstone = {"_id": document_id, "_deleted": True,
                 "_deleted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        requests.post(
            f"{Config.DIAMDB_URL}/{tenant_id}/collection/{collection_name}",
            json=tombstone, timeout=10,
        )
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "diamDB engine unavailable"}), 503

    _audit("DOC_DELETED", f"tenant={tenant_id} doc={document_id}", user_id=g.user["id"])
    return jsonify({"message": f"Document {document_id} tombstoned (GDPR delete)"}), 200


@app.route("/api/v1/<tenant_id>/stats", methods=["GET"])
@require_auth
def tenant_stats(tenant_id):
    valid, err = _validate_identifier(tenant_id, "tenant_id")
    if not valid:
        return jsonify({"error": err}), 400
    if not _has_tenant_access(g.user, tenant_id):
        return jsonify({"error": "Access to this tenant is forbidden"}), 403

    try:
        resp = requests.get(f"{Config.DIAMDB_URL}/{tenant_id}/stats", timeout=10)
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "diamDB engine unavailable"}), 503
    try:
        return jsonify(resp.json()), resp.status_code
    except ValueError:
        return jsonify({"data": resp.text}), resp.status_code


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@app.route("/api/v1/admin/audit", methods=["GET"])
@require_auth
@require_admin
def admin_audit():
    db = _audit_db()
    rows = db.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT 200"
    ).fetchall()
    db.close()
    return jsonify({"entries": [dict(r) for r in rows]}), 200


@app.route("/api/v1/admin/users", methods=["GET"])
@require_auth
@require_admin
def admin_users():
    db = _users_db()
    rows = db.execute(
        "SELECT id, email, role, failed_attempts, locked_until, created_at FROM users"
    ).fetchall()
    db.close()
    return jsonify({"users": [dict(r) for r in rows]}), 200


# ---------------------------------------------------------------------------
# Error handlers (no information leakage)
# ---------------------------------------------------------------------------

@app.errorhandler(400)
def _err_400(e):
    return jsonify({"error": "Bad request"}), 400


@app.errorhandler(404)
def _err_404(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(405)
def _err_405(e):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(413)
def _err_413(e):
    return jsonify({"error": "Payload too large (max 1MB)"}), 413


@app.errorhandler(429)
def _err_429(e):
    return jsonify({"error": "Rate limit exceeded. Please slow down."}), 429


@app.errorhandler(500)
def _err_500(e):
    return jsonify({"error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

_init_databases()


if __name__ == "__main__":
    print("Starting diamDB Enterprise Security Gateway on :5000")
    print("Ensure the diamDB engine is running on :8080")
    app.run(host="127.0.0.1", port=5000, debug=True)
