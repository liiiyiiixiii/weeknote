"""应用业务时钟：周次、展示日期和额度统一使用同一时区。"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import AppSettings

TIMEZONE_NAME = AppSettings.from_env().app_timezone

try:
    TIMEZONE = ZoneInfo(TIMEZONE_NAME)
except ZoneInfoNotFoundError as exc:
    raise RuntimeError(f"APP_TIMEZONE 不是有效时区：{TIMEZONE_NAME}") from exc


def now() -> datetime:
    return datetime.now(TIMEZONE)


def today() -> date:
    return now().date()
