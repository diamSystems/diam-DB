# diam-DB Security Test UI

A modern SaaS-style web interface for testing the diam-DB Enterprise Security Gateway.

## Features

### Landing Tab
- Gateway information display
- Connection status indicator
- Health check endpoint

### Auth Tab
- User registration with password policy enforcement
- Login with JWT token generation
- Session management (logout)
- API key display on registration

### Dashboard Tab
- Create tenants
- Write documents to collections
- Read collections and view data
- Full CRUD operations through the gateway

### Security Tab
- **No Authentication Test** — Verifies unauthenticated requests are blocked (401)
- **Path Traversal Test** — Verifies path traversal attacks are blocked (400)
- **Weak Password Test** — Verifies weak passwords are rejected (400)
- **Tenant Isolation Test** — Verifies users cannot access other tenants' data (403)
- **Oversized Payload Test** — Verifies DoS attacks via large payloads are blocked (413)
- **Rate Limiting Test** — Verifies rate limiting is enforced (429)
- **Security Headers Check** — Displays all security headers on responses

## How to Use

### Prerequisites
1. diam-DB engine running on `http://127.0.0.1:8080`
2. Security Gateway running on `http://127.0.0.1:5000`

### Starting the Services

**Terminal 1 — Start diam-DB engine:**
```bash
cd c:\Users\adams\Documents\Projects\diamsys\diam-DB
cargo run --release -- server
```

**Terminal 2 — Start the Security Gateway:**
```bash
cd c:\Users\adams\Documents\Projects\diamsys\diam-DB\example
python app.py
```

### Opening the UI

Simply open `ui.html` in your web browser:
```
c:\Users\adams\Documents\Projects\diamsys\diam-DB\example\ui.html
```

Or double-click the file in File Explorer.

### Testing Workflow

1. **Landing Tab** — Verify gateway is connected and healthy
2. **Auth Tab** — Register a user, then login to get JWT token
3. **Dashboard Tab** — Create a tenant, write documents, read them back
4. **Security Tab** — Run all security tests to verify mitigations

## Security Features Tested

| Feature | Test | Expected Result |
|---------|------|-----------------|
| Authentication | No-auth access | 401 Unauthorized |
| Input Validation | Path traversal | 400 Bad Request |
| Password Policy | Weak password | 400 Bad Request |
| Authorization | Tenant isolation | 403 Forbidden |
| DoS Prevention | Oversized payload | 413 Payload Too Large |
| Rate Limiting | Rapid requests | 429 Too Many Requests |
| Security Headers | Header check | All headers present |

## Technical Details

- **Technology:** Vanilla HTML/CSS/JavaScript + Tailwind CSS CDN
- **No build required:** Open directly in browser
- **JWT Storage:** localStorage (acceptable for test tool)
- **API Base:** `http://localhost:5000/api/v1`
- **XSS Prevention:** Uses `textContent` for rendering API responses

## File Structure

```
example/
├── app.py              # Security Gateway (Flask)
├── ui.html             # Security Test UI (this file)
├── test_security.py    # Automated security test suite
├── requirements.txt     # Python dependencies
└── UI_README.md        # This file
```

## Troubleshooting

**UI shows "Disconnected":**
- Ensure the gateway is running on port 5000
- Check the gateway terminal for errors

**Security tests fail:**
- Ensure you have created at least one tenant first
- Some tests require the gateway to be in a clean state

**Login fails:**
- Ensure password meets policy (12+ chars, uppercase, lowercase, digit, special)
- Check gateway logs for errors

## Notes

- This is a **test UI**, not a production application
- JWT tokens are stored in localStorage (not production-secure)
- Designed for local testing of the security gateway
- All security mitigations are enforced by the gateway, not the UI
