"""Typed application configuration loaded from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")


def _bounded_int(
    environment: Mapping[str, str],
    name: str,
    default: int,
    minimum: int,
    maximum: int | None = None,
) -> int:
    value = max(minimum, int(environment.get(name, str(default))))
    return min(value, maximum) if maximum is not None else value


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Runtime settings shared by the app factory and API routers."""

    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    volc_asr_url: str
    volc_resource_id: str
    volc_api_key: str
    volc_app_key: str
    volc_access_key: str
    app_env: str
    app_secret: str
    app_secret_file: str
    app_public_origin: str
    app_cookie_path: str
    app_db_path: str
    app_timezone: str
    app_legacy_owner_id: str
    release: str
    message_daily_limit: int
    asr_max_seconds: int
    asr_daily_seconds_limit: int
    report_retention_days: int
    usage_retention_days: int
    attachment_parse_concurrency: int
    attachment_upload_admission: int
    allowed_hosts: tuple[str, ...]

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> AppSettings:
        env = os.environ if environment is None else environment
        parse_concurrency = _bounded_int(env, "ATTACHMENT_PARSE_CONCURRENCY", 2, 1, 8)
        upload_admission = _bounded_int(env, "ATTACHMENT_UPLOAD_ADMISSION", 4, parse_concurrency, 16)
        allowed_hosts = tuple(item.strip() for item in env.get("ALLOWED_HOSTS", "*").split(",") if item.strip())
        asr_max_seconds = _bounded_int(env, "ASR_MAX_SECONDS", 120, 10, 600)
        return cls(
            deepseek_api_key=env.get("DEEPSEEK_API_KEY", ""),
            deepseek_base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_model=env.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            volc_asr_url=env.get("VOLC_ASR_URL", "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"),
            volc_resource_id=env.get("VOLC_RESOURCE_ID", "volc.seedasr.sauc.duration"),
            volc_api_key=env.get("VOLC_API_KEY", ""),
            volc_app_key=env.get("VOLC_APP_KEY", ""),
            volc_access_key=env.get("VOLC_ACCESS_KEY", ""),
            app_env=env.get("APP_ENV", "development").lower(),
            app_secret=env.get("APP_SECRET", ""),
            app_secret_file=env.get("APP_SECRET_FILE", ""),
            app_public_origin=env.get("APP_PUBLIC_ORIGIN", "").rstrip("/"),
            app_cookie_path=env.get("APP_COOKIE_PATH", "/"),
            app_db_path=env.get("APP_DB_PATH", ""),
            app_timezone=(env.get("APP_TIMEZONE") or env.get("LIMIT_TIMEZONE") or "Asia/Shanghai").strip()
            or "Asia/Shanghai",
            app_legacy_owner_id=env.get("APP_LEGACY_OWNER_ID", "").strip(),
            release=env.get("APP_RELEASE", "0.1.0"),
            message_daily_limit=_bounded_int(env, "MESSAGE_DAILY_LIMIT", 10, 1, 100),
            asr_max_seconds=asr_max_seconds,
            asr_daily_seconds_limit=_bounded_int(
                env,
                "ASR_DAILY_SECONDS_LIMIT",
                600,
                asr_max_seconds,
                86_400,
            ),
            report_retention_days=_bounded_int(env, "REPORT_RETENTION_DAYS", 365, 0),
            usage_retention_days=_bounded_int(env, "USAGE_RETENTION_DAYS", 90, 0),
            attachment_parse_concurrency=parse_concurrency,
            attachment_upload_admission=upload_admission,
            allowed_hosts=allowed_hosts or ("*",),
        )
