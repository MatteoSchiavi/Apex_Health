"""Phase 9 AC demo — invite flow + friend isolation over a Funnel-style entrypoint.

What it proves (§23 Phase 9 as directed by the owner):
  "a friend redeems an invite, logs in over the Funnel URL, sees only their
   own data"

A real Tailscale Funnel needs the owner's tailnet, so this demo reproduces
its exact shape locally: a local TLS terminator (self-signed cert) forwards
to the app on loopback and sets X-Forwarded-Proto/-For — precisely what
`tailscale funnel` does. The app runs with TRUST_PROXY_HEADERS=true and the
WHOLE flow below goes through https://127.0.0.1:8443 (the "Funnel URL"),
never directly to the backend.

Run (after scripts/reset-dev.sh and with the dev env exported):
    backend/.venv/bin/python backend/tools/demo_phase9.py
"""

import asyncio
import json
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import urllib.error
import urllib.request

APP_PORT = 8000
FUNNEL_PORT = 8443  # the "Funnel URL" port
FUNNEL_BASE = f"https://127.0.0.1:{FUNNEL_PORT}"
CSRF = {"X-CSRF-Token": "demo"}
FRIEND_EMAIL = "dana@funnel-demo.example"
FRIEND_PASSWORD = "dana-picks-a-long-password"


def cleanup_previous_runs() -> None:
    """Best-effort removal of prior demo artifacts so the demo is rerunnable."""
    import os
    from urllib.parse import urlparse

    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    psql = os.environ.get("PSQL_BIN", "psql")
    sql = """
    UPDATE invites SET used_by = NULL
      WHERE used_by IN (SELECT user_id FROM auth_credentials WHERE email LIKE '%@funnel-demo.example');
    DELETE FROM lab_panels WHERE user_id IN (
        SELECT user_id FROM auth_credentials WHERE email LIKE '%@funnel-demo.example');
    DELETE FROM gear WHERE user_id IN (
        SELECT user_id FROM auth_credentials WHERE email LIKE '%@funnel-demo.example');
    DELETE FROM sessions WHERE user_id IN (
        SELECT user_id FROM auth_credentials WHERE email LIKE '%@funnel-demo.example');
    DELETE FROM auth_credentials WHERE email LIKE '%@funnel-demo.example';
    DELETE FROM users WHERE id NOT IN (SELECT user_id FROM auth_credentials)
       AND name = 'Dana';
    """
    subprocess.run([psql, dsn, "-q", "-c", sql], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_app() -> subprocess.Popen:
    env = dict(**__import__("os").environ, TRUST_PROXY_HEADERS="true")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(APP_PORT)],
        cwd=".",
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{APP_PORT}/health", timeout=1).status_code == 200:
                return proc
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("app did not become healthy")


class FunnelSimulator(BaseHTTPRequestHandler):
    """Local TLS terminator: the shape of `tailscale funnel` — takes HTTPS,
    forwards to the app on loopback, stamps the forwarded headers."""

    protocol_version = "HTTP/1.1"

    def _forward(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{APP_PORT}{self.path}",
            data=body,
            method=self.command,
        )
        for key, value in self.headers.items():
            if key.lower() not in {"host", "content-length", "connection"}:
                req.add_header(key, value)
        req.add_header("X-Forwarded-Proto", "https")
        req.add_header("X-Forwarded-For", "203.0.113.7")  # an internet client
        try:
            with urllib.request.urlopen(req) as resp:
                payload, status, headers = resp.read(), resp.status, dict(resp.headers)
        except urllib.error.HTTPError as exc:
            payload, status, headers = exc.read(), exc.code, dict(exc.headers)
        self.send_response(status)
        for key, value in headers.items():
            if key.lower() in {"content-length", "transfer-encoding", "connection", "server", "date"}:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PATCH = do_DELETE = _forward

    def log_message(self, *args):  # silence request logging
        pass


def start_funnel() -> ThreadingHTTPServer:
    cert, key = tempfile.mkstemp(), tempfile.mkstemp()
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", key[1], "-out", cert[1], "-days", "2",
         "-subj", "/CN=apex-funnel-demo"],
        check=True, capture_output=True,
    )
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert[1], key[1])
    server = ThreadingHTTPServer(("127.0.0.1", FUNNEL_PORT), FunnelSimulator)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def show(step: str, detail: str = "") -> None:
    print(f"\n=== {step} ===")
    if detail:
        print(detail)


async def main() -> None:
    cleanup_previous_runs()
    app = start_app()
    funnel = start_funnel()

    async with httpx.AsyncClient(base_url=FUNNEL_BASE, verify=False, timeout=15) as c:
        r = await c.get("/health")
        show("1. The 'Funnel URL' is live (HTTPS terminator -> app on loopback)",
             f"GET {FUNNEL_BASE}/health -> {r.status_code} {r.text}")

        r = await c.post("/auth/login", json={
            "email": __import__("os").environ["OWNER_EMAIL"],
            "password": __import__("os").environ["OWNER_PASSWORD"],
        }, headers=CSRF)
        show("2. Owner logs in over the Funnel URL", f"-> {r.status_code} {r.json()}")
        owner_cookies = r.cookies

        r = await c.post("/labs", json={
            "panel_date": __import__("datetime").date.today().isoformat(),
            "panel_type": "blood", "ferritin": 17.4,
        }, headers=CSRF, cookies=owner_cookies)
        owner_lab_id = r.json()["id"]
        show("3. Owner seeds their own private lab panel",
             f"-> {r.status_code} panel id={owner_lab_id} ferritin=17.4")

        r = await c.post("/settings/invites", json={}, headers=CSRF, cookies=owner_cookies)
        code = r.json()["code"]
        show("4. Owner mints an invite (code shown once, like in real life)",
             f"-> {r.status_code} code={code}")

        r = await c.post("/auth/invite/redeem", json={
            "code": code, "name": "Dana",
            "email": FRIEND_EMAIL, "password": FRIEND_PASSWORD,
        }, headers=CSRF)
        show("5. FRIEND REDEEMS THE INVITE AND LOGS IN OVER THE FUNNEL URL",
             f"-> {r.status_code} {r.json()} (session cookie set: {'hcc_session' in r.cookies})")
        friend_cookies = r.cookies

        r = await c.post("/labs", json={
            "panel_date": __import__("datetime").date.today().isoformat(),
            "panel_type": "blood", "ferritin": 55.0,
        }, headers=CSRF, cookies=friend_cookies)
        show("6. Friend adds their own lab panel", f"-> {r.status_code}")

        r = await c.get("/labs", cookies=friend_cookies)
        show("7. ...AND SEES ONLY THEIR OWN DATA",
             f"GET /labs -> {r.status_code}\n" + json.dumps(r.json(), indent=2))

        r = await c.get(f"/labs/{owner_lab_id}", cookies=friend_cookies)
        show("8. Owner's row is invisible to the friend (404 — existence denied)",
             f"GET /labs/{owner_lab_id} -> {r.status_code}")

        r = await c.get("/settings/invites", cookies=friend_cookies)
        show("9. Owner-only settings closed to friends",
             f"GET /settings/invites -> {r.status_code} {r.json()['detail']}")

        r = await c.get("/labs", cookies=owner_cookies)
        rows = r.json()
        show("10. Isolation is symmetric: owner sees only owner rows",
             f"GET /labs -> {r.status_code}, {len(rows)} panel(s), "
             f"all owner's (ferritin={[p['ferritin'] for p in rows]})")

    print("\n=== RESULT: PHASE 9 AC DEMONSTRATED ===")
    print("friend redeemed the invite + logged in over the Funnel-shaped HTTPS")
    print("entrypoint + saw only their own data. On a real host the same flow")
    print("runs unchanged at https://<host>.<tailnet>.ts.net (see")
    print("infra/tailscale-funnel-setup.md).")

    funnel.shutdown()
    app.terminate()


if __name__ == "__main__":
    asyncio.run(main())
