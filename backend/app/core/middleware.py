"""ASGI middleware used by the Weeknote application."""

import asyncio

from fastapi.responses import JSONResponse


class AttachmentAdmissionMiddleware:
    """Bound uploads before FastAPI parses multipart bodies into spooled files."""

    def __init__(self, app, *, limit: int):
        self.app = app
        self._slots = asyncio.Semaphore(limit)

    async def __call__(self, scope, receive, send):
        is_upload = (
            scope.get("type") == "http"
            and scope.get("method", "").upper() == "POST"
            and scope.get("path") == "/api/attachments"
        )
        if not is_upload:
            await self.app(scope, receive, send)
            return
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=0.01)
        except TimeoutError:
            response = JSONResponse(
                {"detail": "附件处理队列已满，请稍后重试"},
                status_code=503,
                headers={"Retry-After": "2"},
            )
            await response(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            self._slots.release()
