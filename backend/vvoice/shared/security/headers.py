from __future__ import annotations

from ipaddress import ip_address
import re

from fastapi import Request, Response


APPLICATION_CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "base-uri 'none'",
        "object-src 'none'",
        "frame-src 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "script-src 'self'",
        "script-src-elem 'self'",
        "script-src-attr 'none'",
        "style-src 'self'",
        "style-src-elem 'self'",
        "style-src-attr 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "media-src 'self' blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "worker-src 'self' blob:",
        "manifest-src 'self'",
    )
)

API_DOCS_CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'none'",
        "base-uri 'none'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "script-src 'unsafe-inline' https://cdn.jsdelivr.net",
        "script-src-attr 'none'",
        "style-src 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
        "img-src data: https://fastapi.tiangolo.com",
        "font-src https://fonts.gstatic.com",
        "connect-src 'self'",
    )
)

_BROWSER_SECURITY_HEADERS = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Origin-Agent-Cluster": "?1",
    "Permissions-Policy": (
        "microphone=(self), camera=(), geolocation=(), payment=(), serial=(), usb=()"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-DNS-Prefetch-Control": "off",
    "X-Frame-Options": "DENY",
    "X-Permitted-Cross-Domain-Policies": "none",
    "X-XSS-Protection": "0",
}


def apply_browser_security_headers(request: Request, response: Response) -> None:
    for name, value in _BROWSER_SECURITY_HEADERS.items():
        response.headers[name] = value

    response.headers["Content-Security-Policy"] = _content_security_policy(
        request,
        style_nonce=getattr(request.state, "style_nonce", None),
    )
    if request.url.path.startswith("/api/v1/auth/"):
        response.headers["Cache-Control"] = "no-store"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


def _content_security_policy(request: Request, *, style_nonce: str | None = None) -> str:
    path = request.url.path
    if path == "/docs" or path.startswith("/docs/") or path == "/redoc":
        return API_DOCS_CONTENT_SECURITY_POLICY
    policy = APPLICATION_CONTENT_SECURITY_POLICY
    websocket_source = _same_origin_websocket_source(request)
    if websocket_source:
        policy = policy.replace(
            "connect-src 'self'",
            f"connect-src 'self' {websocket_source}",
        )
    if not style_nonce:
        return policy
    return policy.replace(
        "style-src-elem 'self'",
        f"style-src-elem 'self' 'nonce-{style_nonce}'",
    )


def _same_origin_websocket_source(request: Request) -> str | None:
    host = request.url.hostname
    if not host:
        return None

    try:
        parsed_ip = ip_address(host)
    except ValueError:
        try:
            csp_host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return None
        if not re.fullmatch(r"[A-Za-z0-9._-]+", csp_host):
            return None
    else:
        csp_host = f"[{parsed_ip.compressed}]" if parsed_ip.version == 6 else parsed_ip.compressed

    try:
        port = request.url.port
    except ValueError:
        return None
    authority = f"{csp_host}:{port}" if port else csp_host
    scheme = "wss" if request.url.scheme == "https" else "ws"
    return f"{scheme}://{authority}"
