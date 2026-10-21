"""Teamspace - a small, fictional team workspace admin console.

All data is simulated: the company "Lumen Labs" and every person in it are
fictional. State lives in memory and resets when the server restarts (or via
POST /api/reset).

Run:  python examples/teamspace/server.py --port 4100
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import mimetypes
import re
import secrets
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

ROOT = Path(__file__).resolve().parent
PAGES = ROOT / "pages"
ASSETS = ROOT / "assets"

ACCOUNT_EMAIL = "admin@lumenlabs.example"
ACCOUNT_PASSWORD = "teamspace-demo"
ACCOUNT_NAME = "Alex Morgan"
COOKIE_NAME = "ts_session"

ROLES = {"viewer": "Viewer", "contributor": "Contributor", "admin": "Workspace admin"}
PROJECT_NAMES = ["Orion", "Vega", "Lyra", "Atlas-Retail"]
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

SEED_MEMBERS = [
    {"id": "m1", "name": "Alex Morgan", "email": "admin@lumenlabs.example", "role": "admin", "status": "Active", "lastActive": "Just now"},
    {"id": "m2", "name": "Jordan Lee", "email": "jordan.lee@lumenlabs.example", "role": "contributor", "status": "Active", "lastActive": "2 hours ago"},
    {"id": "m3", "name": "Samira Haddad", "email": "samira.haddad@lumenlabs.example", "role": "admin", "status": "Active", "lastActive": "Yesterday"},
    {"id": "m4", "name": "Tomas Rivera", "email": "tomas.rivera@lumenlabs.example", "role": "contributor", "status": "Active", "lastActive": "3 days ago"},
    {"id": "m5", "name": "Mei Tanaka", "email": "mei.tanaka@lumenlabs.example", "role": "viewer", "status": "Active", "lastActive": "Last week"},
    {"id": "m6", "name": "Oskar Lindqvist", "email": "oskar.lindqvist@lumenlabs.example", "role": "viewer", "status": "Inactive", "lastActive": "2 months ago"},
]

SEED_PROJECTS = [
    {"id": "p1", "name": "Orion", "description": "Customer onboarding redesign", "owner": "Samira Haddad", "members": 5, "updated": "Today"},
    {"id": "p2", "name": "Vega", "description": "Billing service migration", "owner": "Jordan Lee", "members": 4, "updated": "Yesterday"},
    {"id": "p3", "name": "Lyra", "description": "Research notes and interview library", "owner": "Mei Tanaka", "members": 3, "updated": "3 days ago"},
    {"id": "p4", "name": "Atlas-Retail", "description": "Retail partner portal", "owner": "Tomas Rivera", "members": 2, "updated": "Last week"},
]

# (href, label) grouped under headings; used to render the left navigation.
NAV = [
    ("Workspace", [("/home", "Home"), ("/projects", "Projects")]),
    ("People", [("/members", "Members"), ("/groups", "Groups")]),
    ("Admin", [("/settings", "Settings"), ("/billing", "Billing")]),
]

# path -> (page file, page title, nav item that is highlighted, page script)
ROUTES = {
    "/home": ("home.html", "Home", "/home", "home.js"),
    "/projects": ("projects.html", "Projects", "/projects", "projects.js"),
    "/members": ("members.html", "Members", "/members", "members.js"),
    "/members/invite": ("invite.html", "Invite people", "/members", "invite.js"),
    "/groups": ("groups.html", "Groups", "/groups", None),
    "/settings": ("settings.html", "Settings", "/settings", None),
    "/billing": ("billing.html", "Billing", "/billing", None),
}


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.sessions: set[str] = set()
        self.reset()

    def reset(self) -> None:
        self.members = copy.deepcopy(SEED_MEMBERS)
        self.projects = copy.deepcopy(SEED_PROJECTS)
        self.invites: list[dict] = []
        self.next_id = 1


STATE = State()


def member_view(m: dict) -> dict:
    out = dict(m)
    out["roleLabel"] = ROLES.get(m["role"], m["role"])
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def render_nav(active: str) -> str:
    parts = []
    for heading, items in NAV:
        hid = "nav-" + heading.lower()
        parts.append(f'<div class="nav-group"><h2 class="nav-heading" id="{hid}">{heading}</h2><ul aria-labelledby="{hid}">')
        for href, label in items:
            current = ' aria-current="page" class="active"' if href == active else ""
            parts.append(f'<li><a href="{href}"{current}>{label}</a></li>')
        parts.append("</ul></div>")
    return "".join(parts)


def render_page(path: str) -> str:
    page_file, title, active, script = ROUTES[path]
    layout = (PAGES / "layout.html").read_text(encoding="utf-8")
    content = (PAGES / page_file).read_text(encoding="utf-8")
    initials = "".join(w[0] for w in ACCOUNT_NAME.split())[:2]
    scripts = '<script src="/assets/app.js"></script>'
    if script:
        scripts += f'<script src="/assets/{script}"></script>'
    return (
        layout.replace("{{title}}", html.escape(title))
        .replace("{{nav}}", render_nav(active))
        .replace("{{user_name}}", html.escape(ACCOUNT_NAME))
        .replace("{{user_email}}", html.escape(ACCOUNT_EMAIL))
        .replace("{{user_initials}}", html.escape(initials))
        .replace("{{content}}", content)
        .replace("{{scripts}}", scripts)
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "Teamspace/1.0"

    # ---- helpers -------------------------------------------------------
    def log_message(self, fmt: str, *args) -> None:  # quieter console
        if not getattr(self.server, "quiet", False):
            super().log_message(fmt, *args)

    def session_token(self) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:
            return None
        morsel = cookie.get(COOKIE_NAME)
        return morsel.value if morsel else None

    def signed_in(self) -> bool:
        token = self.session_token()
        with STATE.lock:
            return bool(token) and token in STATE.sessions

    def send_body(self, status: int, body: bytes, ctype: str, headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, status: int, data) -> None:
        self.send_body(status, json.dumps(data).encode("utf-8"), "application/json; charset=utf-8")

    def send_html(self, status: int, text: str, headers: dict | None = None) -> None:
        self.send_body(status, text.encode("utf-8"), "text/html; charset=utf-8", headers)

    def redirect(self, location: str, headers: dict | None = None) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def read_json(self):
        try:
            return json.loads(self.read_body() or b"{}")
        except json.JSONDecodeError:
            return None

    def not_found(self) -> None:
        text = (PAGES / "not_found.html").read_text(encoding="utf-8")
        self.send_html(HTTPStatus.NOT_FOUND, text)

    # ---- routing -------------------------------------------------------
    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        path = url.path.rstrip("/") or "/"

        if path.startswith("/assets/"):
            return self.serve_asset(path[len("/assets/"):])
        if path == "/favicon.ico":
            return self.serve_asset("favicon.svg")
        if path.startswith("/api/"):
            return self.api_get(path)
        if path == "/login":
            if self.signed_in():
                return self.redirect("/home")
            text = (PAGES / "login.html").read_text(encoding="utf-8")
            return self.send_html(HTTPStatus.OK, text)
        if path == "/":
            return self.redirect("/home" if self.signed_in() else "/login")
        if path in ROUTES:
            if not self.signed_in():
                return self.redirect("/login?next=" + quote(path))
            return self.send_html(HTTPStatus.OK, render_page(path))
        return self.not_found()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path.rstrip("/") or "/"
        if path == "/login":
            return self.handle_login()
        if path == "/logout":
            token = self.session_token()
            with STATE.lock:
                STATE.sessions.discard(token or "")
            return self.redirect("/login", {"Set-Cookie": f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})
        if path == "/api/reset":
            if self.client_address[0] != "127.0.0.1":
                return self.send_json(HTTPStatus.FORBIDDEN, {"error": "Reset is only allowed from 127.0.0.1."})
            with STATE.lock:
                STATE.reset()
            return self.send_json(HTTPStatus.OK, {"ok": True})
        if path == "/api/invites":
            if not self.signed_in():
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Not signed in."})
            return self.create_invite()
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    # ---- handlers ------------------------------------------------------
    def serve_asset(self, name: str) -> None:
        target = (ASSETS / name).resolve()
        if ASSETS.resolve() not in target.parents or not target.is_file():
            return self.send_body(HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix == ".js":
            ctype = "text/javascript"
        if ctype.startswith("text/") or target.suffix in (".svg",):
            ctype += "; charset=utf-8"
        self.send_body(HTTPStatus.OK, target.read_bytes(), ctype)

    def handle_login(self) -> None:
        form = parse_qs(self.read_body().decode("utf-8", "replace"))
        email = (form.get("email") or [""])[0].strip().lower()
        password = (form.get("password") or [""])[0]
        nxt = (form.get("next") or [""])[0]
        if nxt not in ROUTES:
            nxt = "/home"
        if email == ACCOUNT_EMAIL and password == ACCOUNT_PASSWORD:
            token = secrets.token_urlsafe(24)
            with STATE.lock:
                STATE.sessions.add(token)
            cookie = f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax"
            return self.redirect(nxt, {"Set-Cookie": cookie})
        query = "error=1"
        if nxt != "/home":
            query += "&next=" + quote(nxt)
        return self.redirect("/login?" + query)

    def api_get(self, path: str) -> None:
        if not self.signed_in():
            return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Not signed in."})
        with STATE.lock:
            if path == "/api/me":
                return self.send_json(HTTPStatus.OK, {"name": ACCOUNT_NAME, "email": ACCOUNT_EMAIL, "role": "admin", "workspace": "Lumen Labs"})
            if path == "/api/members":
                return self.send_json(HTTPStatus.OK, {"members": [member_view(m) for m in STATE.members]})
            if path == "/api/invites":
                return self.send_json(HTTPStatus.OK, {"invites": copy.deepcopy(STATE.invites)})
            if path == "/api/projects":
                return self.send_json(HTTPStatus.OK, {"projects": copy.deepcopy(STATE.projects)})
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def create_invite(self) -> None:
        body = self.read_json()
        if not isinstance(body, dict):
            return self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Request body must be a JSON object."})
        email = str(body.get("email") or "").strip()
        name = str(body.get("name") or "").strip()
        role_in = str(body.get("role") or "").strip()
        projects = body.get("projects") or []
        welcome = body.get("welcomeEmail", True)

        errors = {}
        if not email:
            errors["email"] = "Enter an email address."
        elif not EMAIL_RE.match(email):
            errors["email"] = "Enter a valid email address."
        role = None
        for key, label in ROLES.items():
            if role_in.lower() in (key, label.lower()):
                role = key
        if role is None:
            errors["role"] = "Choose a role."
        if not isinstance(projects, list) or any(p not in PROJECT_NAMES for p in projects):
            errors["projects"] = "Unknown project."
        if errors:
            return self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": next(iter(errors.values())), "fields": errors})

        with STATE.lock:
            if any(m["email"].lower() == email.lower() for m in STATE.members):
                return self.send_json(HTTPStatus.CONFLICT, {"error": f"{email} is already a member of this workspace.", "fields": {"email": "Already a member."}})
            n = STATE.next_id
            STATE.next_id += 1
            invite = {
                "id": f"inv-{n}",
                "email": email,
                "name": name,
                "role": role,
                "roleLabel": ROLES[role],
                "projects": [p for p in PROJECT_NAMES if p in projects],
                "welcomeEmail": bool(welcome),
                "status": "Invited",
                "invitedBy": ACCOUNT_EMAIL,
                "createdAt": now_iso(),
            }
            STATE.invites.append(invite)
            STATE.members.append({
                "id": f"m-inv-{n}",
                "name": name or email.split("@")[0],
                "email": email,
                "role": role,
                "status": "Invited",
                "lastActive": "Never",
            })
        self.send_json(HTTPStatus.CREATED, {"invite": invite})


def main() -> None:
    parser = argparse.ArgumentParser(description="Teamspace demo admin console")
    parser.add_argument("--port", type=int, default=4100)
    parser.add_argument("--quiet", action="store_true", help="do not log each request")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.quiet = args.quiet
    print(f"Teamspace running at http://127.0.0.1:{args.port}/login", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
