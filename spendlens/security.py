"""Web hardening that sits around the API: throttling of failed sign-ins, a cross-site request check, and the
browser security headers. app.py calls `install(app, origins)`; the tests build their own app and call it too.

- `LOGIN` / `LOGIN_PER_IP` / `RESET` throttle failed attempts in memory (one process; they reset on restart).
- `install` adds one middleware that refuses a state-changing API call whose `Origin` is a different site
  (the session cookie is SameSite=Lax, which still treats every localhost port as the same site), and puts
  nosniff / frame / referrer headers on every response and a Content-Security-Policy on HTML pages.
"""
import base64
import hashlib
import re
import threading
import time
from collections import deque
from pathlib import Path

from fastapi.responses import JSONResponse

API = "/spendlens/api"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class Throttle:
    """At most `limit` failures per key within `window` seconds; then `retry_after(key)` says how long to wait."""

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self._fails: dict = {}
        self._lock = threading.Lock()

    def _recent(self, key, now):
        q = self._fails.get(key)
        if q is None:
            return None
        while q and now - q[0] >= self.window:
            q.popleft()
        if not q:
            del self._fails[key]
            return None
        return q

    def retry_after(self, key) -> int:
        """Seconds until `key` may try again (0 = now)."""
        now = time.monotonic()
        with self._lock:
            q = self._recent(key, now)
            if q is None or len(q) < self.limit:
                return 0
            return max(1, int(self.window - (now - q[0])) + 1)

    def fail(self, key):
        now = time.monotonic()
        with self._lock:
            q = self._recent(key, now)
            if q is None:
                q = self._fails[key] = deque()
            q.append(now)

    def clear(self, key):
        with self._lock:
            self._fails.pop(key, None)

    def reset(self):
        with self._lock:
            self._fails.clear()


LOGIN = Throttle(5, 15 * 60)            # per (client address, email): a guessed password, five tries
LOGIN_PER_IP = Throttle(20, 15 * 60)    # per client address, across emails: spraying many accounts
RESET = Throttle(5, 15 * 60)            # per client address: wrong password-reset codes


def reset_throttles():
    for t in (LOGIN, LOGIN_PER_IP, RESET):
        t.reset()


def client_ip(request) -> str:
    return request.client.host if request.client else ""


# ---------------------------------------------------------------- cross-site request check

def _norm(origin: str) -> str:
    return origin.strip().rstrip("/").lower()


def origin_allowed(origin: str, request, allowed: set) -> bool:
    """A request's Origin is fine when it is this server itself (as the browser addressed it, directly or through
    the dev proxy) or one of the configured cross-origin frontends. "null" (sandboxed pages, file://) is not."""
    o = _norm(origin)
    if o in allowed:
        return True
    scheme = request.url.scheme
    hosts = [request.headers.get("host", "")]
    # Set by the Vite dev proxy (xfwd); a cross-site page can't add it without a CORS preflight, which fails.
    hosts += [h.strip() for h in request.headers.get("x-forwarded-host", "").split(",")]
    return any(h and o in (_norm(f"{scheme}://{h}"), _norm(f"http://{h}"), _norm(f"https://{h}")) for h in hosts)


# ---------------------------------------------------------------- security headers

def inline_script_hashes(index_html: Path | None) -> list[str]:
    """CSP hashes of the built index.html's inline scripts (the pre-paint theme script), so no 'unsafe-inline'."""
    if not index_html or not index_html.is_file():
        return []
    html = index_html.read_text(encoding="utf-8")
    bodies = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S | re.I)
    return [f"'sha256-{base64.b64encode(hashlib.sha256(b.encode('utf-8')).digest()).decode()}'" for b in bodies if b.strip()]


def content_security_policy(script_hashes: list[str]) -> str:
    return "; ".join([
        "default-src 'self'",
        "script-src 'self' " + " ".join(script_hashes) if script_hashes else "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",   # React style={{...}} props are inline styles
        "font-src 'self' data: https://fonts.gstatic.com",
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "frame-src 'self' blob:",       # MF Analysis shows a stored Morningstar PDF in an iframe
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
    ])


HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}
DOC_PATHS = ("/docs", "/redoc")   # Swagger / ReDoc load their scripts from a CDN, so they get no CSP


def install(app, origins=(), index_html: Path | None = None):
    allowed = {_norm(o) for o in origins if o.strip()}
    csp = content_security_policy(inline_script_hashes(index_html))

    @app.middleware("http")
    async def _harden(request, call_next):
        if request.method in UNSAFE_METHODS and request.url.path.startswith(API):
            origin = request.headers.get("origin")
            if origin is not None and not origin_allowed(origin, request, allowed):
                return JSONResponse({"detail": "Cross-site request refused."}, status_code=403)
        response = await call_next(request)
        for k, v in HEADERS.items():
            response.headers.setdefault(k, v)
        # HTML only: a CSP on the PDF response would stop the browser's own PDF viewer (object-src).
        if response.headers.get("content-type", "").startswith("text/html") and not request.url.path.startswith(DOC_PATHS):
            response.headers.setdefault("Content-Security-Policy", csp)
        return response
