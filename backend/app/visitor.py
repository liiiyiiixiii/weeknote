"""匿名访客身份、来源 IP 识别与跨站请求防护。"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from http.cookies import SimpleCookie

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from app.core.config import AppSettings

COOKIE_NAME = "ask_visitor"
SETTINGS = AppSettings.from_env()
COOKIE_PATH = SETTINGS.app_cookie_path
PUBLIC_ORIGIN = SETTINGS.app_public_origin
APP_ENV = SETTINGS.app_env
_SECRET = SETTINGS.app_secret
_SECRET_FILE = SETTINGS.app_secret_file

if not _SECRET and _SECRET_FILE:
    try:
        _SECRET = open(_SECRET_FILE, encoding="utf-8").read().strip()
    except OSError as exc:
        raise RuntimeError("无法读取 APP_SECRET_FILE") from exc

if APP_ENV == "production" and len(_SECRET) < 32:
    raise RuntimeError("生产环境必须配置至少 32 个字符的 APP_SECRET")
if not _SECRET:
    _SECRET = secrets.token_urlsafe(32)


def _signature(token: str) -> str:
    return hmac.new(_SECRET.encode(), token.encode(), hashlib.sha256).hexdigest()


def _signed_token(token: str) -> str:
    return f"{token}.{_signature(token)}"


def _validate_cookie(value: str) -> str | None:
    try:
        token, signature = value.rsplit(".", 1)
    except ValueError:
        return None
    if len(token) < 24 or len(token) > 100:
        return None
    if not hmac.compare_digest(_signature(token), signature):
        return None
    return token


def _cookie_token(headers: Headers) -> str | None:
    raw = headers.get("cookie", "")
    if not raw:
        return None
    cookies = SimpleCookie()
    try:
        cookies.load(raw)
    except Exception:
        return None
    morsel = cookies.get(COOKIE_NAME)
    return _validate_cookie(morsel.value) if morsel else None


def _peer_is_loopback(scope: dict) -> bool:
    client = scope.get("client")
    if not client:
        return False
    try:
        return ipaddress.ip_address(client[0]).is_loopback
    except ValueError:
        return False


def client_ip(scope: dict, headers: Headers) -> str:
    """仅在请求来自本机反代时信任 X-Real-IP，避免伪造来源。"""
    candidate = ""
    if _peer_is_loopback(scope):
        candidate = headers.get("x-real-ip", "").strip()
    if not candidate and scope.get("client"):
        candidate = str(scope["client"][0])
    try:
        return ipaddress.ip_address(candidate).compressed
    except ValueError:
        return "unknown"


def visitor_id(token: str) -> str:
    return hmac.new(_SECRET.encode(), ("visitor:" + token).encode(), hashlib.sha256).hexdigest()


def rate_limit_key(ip: str) -> str:
    return hmac.new(_SECRET.encode(), ("ip:" + ip).encode(), hashlib.sha256).hexdigest()


def websocket_origin_allowed(headers: Headers) -> bool:
    if not PUBLIC_ORIGIN:
        return True
    return headers.get("origin", "").rstrip("/") == PUBLIC_ORIGIN


class VisitorMiddleware:
    """向请求注入匿名隔离身份，并拒绝浏览器跨站写请求。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        token = _cookie_token(headers)
        new_cookie = token is None
        if token is None:
            token = secrets.token_urlsafe(32)

        scope.setdefault("state", {})["visitor_id"] = visitor_id(token)
        scope["state"]["client_ip"] = client_ip(scope, headers)

        if scope["type"] == "http":
            method = scope.get("method", "GET").upper()
            fetch_site = headers.get("sec-fetch-site", "")
            origin = headers.get("origin", "").rstrip("/")
            cross_site = fetch_site == "cross-site" or (PUBLIC_ORIGIN and origin and origin != PUBLIC_ORIGIN)
            if method not in {"GET", "HEAD", "OPTIONS"} and cross_site:
                response = JSONResponse({"detail": "已拒绝跨站请求"}, status_code=403)
                await response(scope, receive, send)
                return

            async def send_with_cookie(message):
                if new_cookie and message["type"] == "http.response.start":
                    mutable = MutableHeaders(scope=message)
                    secure = APP_ENV == "production" or PUBLIC_ORIGIN.startswith("https://")
                    cookie = (
                        f"{COOKIE_NAME}={_signed_token(token)}; Path={COOKIE_PATH}; "
                        "Max-Age=31536000; HttpOnly; SameSite=Strict"
                    )
                    if secure:
                        cookie += "; Secure"
                    mutable.append("set-cookie", cookie)
                await send(message)

            await self.app(scope, receive, send_with_cookie)
            return

        await self.app(scope, receive, send)
