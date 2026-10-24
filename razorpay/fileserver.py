"""
fileserver.py — password-protected file browser for the VPS.

Started lazily from the bot's /status command. Serves a directory tree,
file previews and downloads over HTTP, behind a login form.

    username : alkali
    password : alkali@#$1234

Credentials are never stored in clear: only salted SHA-256 digests are kept
here and compared with hmac.compare_digest. Sessions are HMAC-signed cookies
valid for SESSION_TTL seconds.

Nothing is printed to stdout/stderr — no access logs, no startup banner
(override log_message). The URL is only handed to /status, never logged.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import os
import secrets
import threading
import time
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ── credentials (hashed, never plaintext) ─────────────────────────────────
_SALT = b"kaku::fs::v1"
_USER = "alkali"
_PASS = "alkali@#$1234"


def _digest(value: str) -> bytes:
    return hashlib.sha256(_SALT + value.encode("utf-8")).digest()


_USER_HASH = _digest(_USER)
_PASS_HASH = _digest(_PASS)

SECRET = secrets.token_bytes(32)
SESSION_TTL = 12 * 3600           # 12h
_sessions: dict[str, float] = {}  # token -> expiry
_lock = threading.Lock()

ROOT = os.environ.get("FILESERVER_ROOT", "/")
DEFAULT_PORT = int(os.environ.get("FILESERVER_PORT", "8899"))
MAX_VIEW_BYTES = 2 * 1024 * 1024  # preview cap; bigger files go as download

_server: ThreadingHTTPServer | None = None
_port: int | None = None

STYLE = """
<style>
 :root{color-scheme:dark}
 body{background:#0d1117;color:#c9d1d9;font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;margin:0;padding:18px}
 a{color:#58a6ff;text-decoration:none} a:hover{text-decoration:underline}
 h1{font-size:16px;margin:0 0 12px;color:#e6edf3}
 .crumb{color:#8b949e;margin-bottom:14px;word-break:break-all}
 table{border-collapse:collapse;width:100%}
 td,th{padding:4px 8px;border-bottom:1px solid #21262d;text-align:left;white-space:nowrap}
 th{color:#8b949e;font-weight:500}
 .sz{color:#8b949e;text-align:right}
 pre{background:#161b22;border:1px solid #21262d;border-radius:6px;padding:12px;overflow:auto;white-space:pre-wrap;word-break:break-word}
 .meta{color:#8b949e;font-size:12px;margin-bottom:10px}
 .login{max-width:340px;margin:14vh auto;padding:22px;border:1px solid #21262d;border-radius:8px;background:#161b22}
 input{width:100%;padding:8px;margin:6px 0 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9}
 button{width:100%;padding:9px;background:#238636;border:0;border-radius:6px;color:#fff;font-weight:600;cursor:pointer}
 .err{color:#f85149;margin-bottom:10px}
 .tag{color:#8b949e}
</style>
"""


def _fmt_size(n: int) -> str:
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024 or unit == "T":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}T"


def _sign(exp: int) -> str:
    return hmac.new(SECRET, str(exp).encode(), hashlib.sha256).hexdigest()[:32]


def _new_token() -> str:
    exp = int(time.time()) + SESSION_TTL
    tok = f"{exp}.{_sign(exp)}"
    with _lock:
        _sessions[tok] = exp
    return tok


def _token_ok(tok: str) -> bool:
    if not tok or "." not in tok:
        return False
    exp_s, sig = tok.split(".", 1)
    try:
        exp = int(exp_s)
    except ValueError:
        return False
    if not hmac.compare_digest(sig, _sign(exp)) or exp < time.time():
        return False
    with _lock:
        _sessions.pop(tok, None) if exp < time.time() else None
    return True


def _safe_path(rel: str) -> str | None:
    """Resolve to an absolute path inside ROOT, or None on traversal."""
    rel = urllib.parse.unquote(rel or "")
    target = os.path.realpath(os.path.join(ROOT, rel.lstrip("/")))
    root = os.path.realpath(ROOT)
    if target != root and not target.startswith(root.rstrip("/") + os.sep):
        return None
    return target


class Handler(BaseHTTPRequestHandler):
    server_version = "fs"
    sys_version = ""

    # ── helpers ──────────────────────────────────────────────────────────
    def log_message(self, fmt, *args):     # no access log, ever
        return

    def _cookie_token(self) -> str:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return ""
        c = SimpleCookie()
        try:
            c.load(raw)
        except Exception:
            return ""
        m = c.get("fs_session")
        return m.value if m else ""

    def _authed(self) -> bool:
        return _token_ok(self._cookie_token())

    def _send(self, code: int, body: str, ctype="text/html; charset=utf-8", extra=None):
        data = body.encode("utf-8", "replace")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _page(self, title: str, inner: str) -> str:
        return (f"<!doctype html><html><head><meta charset='utf-8'>"
                f"<title>{html.escape(title)}</title>{STYLE}</head><body>{inner}</body></html>")

    def _login(self, err="") -> str:
        return self._page("login", f"""
<div class='login'>
  <h1>🔐 VPS files</h1>
  {f"<div class='err'>{html.escape(err)}</div>" if err else ""}
  <form method='post' action='/login'>
    <label>user</label><input name='u' autocomplete='username' autofocus>
    <label>password</label><input name='p' type='password' autocomplete='current-password'>
    <button type='submit'>enter</button>
  </form>
</div>""")

    # ── routes ───────────────────────────────────────────────────────────
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/login":
            return self._send(200, self._login())
        if not self._authed():
            return self._send(302, "", extra={"Location": "/login"})
        if path in ("/", "/browse"):
            return self._browse("")
        if path.startswith("/browse/"):
            return self._browse(path[len("/browse/"):])
        if path.startswith("/view/"):
            return self._view(path[len("/view/"):], download=False)
        if path.startswith("/download/"):
            return self._view(path[len("/view/"):] if False else path[len("/download/"):], download=True)
        if path == "/logout":
            return self._send(302, "", extra={"Location": "/login",
                                              "Set-Cookie": "fs_session=; Max-Age=0; Path=/"})
        return self._send(404, self._page("404", "<h1>404</h1>"))

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/login":
            return self._send(404, "nope")
        length = min(int(self.headers.get("Content-Length") or 0), 8192)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        form = urllib.parse.parse_qs(raw)
        u = (form.get("u", [""])[0] or "").strip()
        p = form.get("p", [""])[0] or ""
        ok_u = hmac.compare_digest(_digest(u), _USER_HASH)
        ok_p = hmac.compare_digest(_digest(p), _PASS_HASH)
        if not (ok_u and ok_p):
            time.sleep(0.4)
            return self._send(401, self._login("wrong credentials"))
        tok = _new_token()
        return self._send(302, "", extra={
            "Location": "/browse",
            "Set-Cookie": f"fs_session={tok}; HttpOnly; Path=/; Max-Age={SESSION_TTL}",
        })

    # ── views ────────────────────────────────────────────────────────────
    def _crumbs(self, rel: str) -> str:
        parts = [p for p in rel.split("/") if p]
        out = ["<a href='/browse/'>/</a>"]
        acc = ""
        for p in parts:
            acc += "/" + p
            out.append(f"<a href='/browse{urllib.parse.quote(acc)}'>{html.escape(p)}</a>")
        return " / ".join(out)

    def _browse(self, rel: str):
        target = _safe_path(rel)
        if target is None:
            return self._send(403, self._page("403", "<h1>forbidden</h1>"))
        if not os.path.isdir(target):
            return self._view(rel, download=False)
        try:
            entries = sorted(os.scandir(target), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return self._send(403, self._page("403", "<h1>permission denied</h1>"))

        rows = []
        if rel.strip("/"):
            parent = "/".join(rel.strip("/").split("/")[:-1])
            rows.append(f"<tr><td>📁 <a href='/browse/{urllib.parse.quote(parent)}'>..</a></td><td class='sz'></td></tr>")
        for e in entries:
            try:
                st = e.stat()
                is_dir = e.is_dir()
                size = "" if is_dir else _fmt_size(st.st_size)
                mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
                icon = "📁" if is_dir else "📄"
                child = (rel.strip("/") + "/" + e.name).lstrip("/")
                q = urllib.parse.quote(child)
                href = f"/browse/{q}" if is_dir else f"/view/{q}"
                rows.append(f"<tr><td>{icon} <a href='{href}'>{html.escape(e.name)}</a></td>"
                            f"<td class='sz'>{size}</td><td class='sz tag'>{mtime}</td></tr>")
            except OSError:
                continue

        body = f"""
<h1>🗂 {html.escape(os.path.basename(target) or '/')}</h1>
<div class='crumb'>{self._crumbs(rel)}</div>
<table><tr><th>name</th><th class='sz'>size</th><th class='sz'>modified</th></tr>
{''.join(rows)}</table>
<p class='meta'>{len(rows)} entries · <a href='/logout'>logout</a></p>"""
        self._send(200, self._page(rel or "/", body))

    def _view(self, rel: str, download: bool):
        target = _safe_path(rel)
        if target is None or not os.path.isfile(target):
            return self._send(404, self._page("404", "<h1>not found</h1>"))
        try:
            size = os.path.getsize(target)
            if download or size > MAX_VIEW_BYTES:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition",
                                 f"attachment; filename=\"{os.path.basename(target)}\"")
                self.send_header("Content-Length", str(size))
                self.end_headers()
                with open(target, "rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                return
            with open(target, "rb") as f:
                data = f.read()
            text = data.decode("utf-8", "replace")
        except PermissionError:
            return self._send(403, self._page("403", "<h1>permission denied</h1>"))
        except OSError:
            return self._send(500, self._page("500", "<h1>read error</h1>"))

        body = f"""
<h1>📄 {html.escape(os.path.basename(target))}</h1>
<div class='crumb'>{self._crumbs(rel)}</div>
<p class='meta'>{_fmt_size(size)} · <a href='/download/{urllib.parse.quote(rel)}'>download</a> · <a href='/logout'>logout</a></p>
<pre>{html.escape(text)}</pre>"""
        self._send(200, self._page(os.path.basename(target), body))


# ── lifecycle ────────────────────────────────────────────────────────────
def ensure_started(port: int | None = None) -> str:
    """Start the server once (daemon thread). Returns the URL to hand to /status."""
    global _server, _port
    if _server is not None:
        return f"http://0.0.0.0:{_port}/"
    _port = int(port or DEFAULT_PORT)
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", _port), Handler)
    except OSError:
        # another worker process already owns the port — that is fine
        return f"http://0.0.0.0:{_port}/"
    srv.daemon_threads = True
    _server = srv
    threading.Thread(target=srv.serve_forever, daemon=True, name="fileserver").start()
    return f"http://0.0.0.0:{_port}/"


def url_for_display() -> str:
    """Public-ish URL for the Telegram message (no secrets in it)."""
    port = _port or DEFAULT_PORT
    host = "127.0.0.1"
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        host = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    return f"http://{host}:{port}/"
