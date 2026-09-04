"""Weeknote FastAPI application factory and compatibility entry point."""

import asyncio
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import agent as agent
from app import storage, visitor
from app.api.common import week_context, week_info
from app.api.routers import assistant, attachments, reports, settings, templates
from app.core.config import AppSettings
from app.core.lifecycle import lifespan
from app.core.middleware import AttachmentAdmissionMiddleware

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"


def _week_info(settings=None) -> dict:
    """Compatibility wrapper for the former module-level helper."""

    return week_info(settings)


def _week_context(info: dict, settings=None) -> str:
    """Compatibility wrapper for the former module-level helper."""

    return week_context(info, settings)


def create_app(settings_override: AppSettings | None = None) -> FastAPI:
    """Build an application instance without changing the public route contract."""

    settings_value = settings_override or AppSettings.from_env()
    application = FastAPI(title="周报助手", version=settings_value.release, lifespan=lifespan)
    application.state.settings = settings_value
    application.state.attachment_parse_slots = asyncio.Semaphore(settings_value.attachment_parse_concurrency)

    # add_middleware inserts new entries before older ones. Keep request-body
    # admission inside host/origin checks but outside multipart parsing.
    application.add_middleware(
        AttachmentAdmissionMiddleware,
        limit=settings_value.attachment_upload_admission,
    )
    application.add_middleware(visitor.VisitorMiddleware)
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings_value.allowed_hosts),
    )

    @application.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    @application.get("/api/health", tags=["system"])
    def health(request: Request):
        return {"status": "ok", "release": request.app.state.settings.release}

    application.include_router(settings.router)
    application.include_router(templates.router)
    application.include_router(assistant.router)
    application.include_router(attachments.router)
    application.include_router(reports.router)
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    storage.init_db()
    storage.cleanup_expired(
        settings_value.report_retention_days,
        settings_value.usage_retention_days,
    )
    return application


DEFAULT_SETTINGS = AppSettings.from_env()

# Compatibility constants retained for integrations that imported them from
# app.main before configuration was centralized.
API_KEY = DEFAULT_SETTINGS.deepseek_api_key
BASE_URL = DEFAULT_SETTINGS.deepseek_base_url
MODEL = DEFAULT_SETTINGS.deepseek_model
APP_RELEASE = DEFAULT_SETTINGS.release
MESSAGE_DAILY_LIMIT = DEFAULT_SETTINGS.message_daily_limit
ASR_DAILY_SECONDS_LIMIT = DEFAULT_SETTINGS.asr_daily_seconds_limit
REPORT_RETENTION_DAYS = DEFAULT_SETTINGS.report_retention_days
USAGE_RETENTION_DAYS = DEFAULT_SETTINGS.usage_retention_days
ATTACHMENT_PARSE_CONCURRENCY = DEFAULT_SETTINGS.attachment_parse_concurrency
ATTACHMENT_UPLOAD_ADMISSION = DEFAULT_SETTINGS.attachment_upload_admission
ALLOWED_HOSTS = list(DEFAULT_SETTINGS.allowed_hosts)

app = create_app(DEFAULT_SETTINGS)
