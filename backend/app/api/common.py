"""Shared API helpers with no route registration side effects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException, Request

from app import clock, storage, template_system, user_settings, visitor
from app.core.config import AppSettings

WEEKDAY_NAMES = "一二三四五六日"


def app_settings(request: Request) -> AppSettings:
    return request.app.state.settings


def week_info(settings: dict | None = None) -> dict:
    today = clock.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    if settings:
        first = user_settings.coerce_date(settings["week_one_start"])
        week_number = user_settings.week_number(monday, first)
    else:
        _, week_number, _ = today.isocalendar()
    return {
        "today": today,
        "weekday": WEEKDAY_NAMES[today.weekday()],
        "week_number": week_number,
        "monday": monday,
        "sunday": sunday,
    }


def week_context(info: dict, settings: dict | None = None) -> str:
    del settings
    return (
        f"今天是 {info['today'].isoformat()}（星期{info['weekday']}）。"
        f"本周是第 {info['week_number']} 周，日期区间为 "
        f"{info['monday'].strftime('%Y.%m.%d')}–{info['sunday'].strftime('%Y.%m.%d')}。"
    )


def sse(event: dict) -> str:
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


def settings_public(owner_id: str, row: dict | None = None) -> dict:
    earliest = storage.earliest_week_start(owner_id)
    defaults = user_settings.settings_defaults(earliest)
    if not row:
        values = defaults
        configured = False
    else:
        values = {
            "week_one_start": row["week_one_start"],
            "purpose_mode": row["purpose_mode"],
            "custom_purpose_name": row.get("custom_purpose_name", ""),
            "custom_purpose_description": row.get("custom_purpose_description", ""),
            "detail_level": row["detail_level"],
            "tone": row["tone"],
            "selected_template_id": row.get("selected_template_id"),
            "onboarding_completed": bool(row.get("onboarding_completed", 0)),
        }
        configured = values["onboarding_completed"]
    current = week_info(values if configured else defaults)
    max_start = (
        min(user_settings.current_monday(), user_settings.coerce_date(earliest))
        if earliest
        else user_settings.current_monday()
    )
    return {
        "configured": configured,
        "settings": values,
        "defaults": defaults,
        "constraints": {
            "latest_week_one_start": max_start.isoformat(),
            "latest_week_one_end": user_settings.week_end(max_start).isoformat(),
            "week_start_day": "monday",
        },
        "current_week": {
            "week_number": current["week_number"],
            "week_start": current["monday"].isoformat(),
            "week_end": current["sunday"].isoformat(),
            "display_label": f"第 {current['week_number']} 周",
        },
        "selected_template_id": values.get("selected_template_id"),
    }


def require_settings(owner_id: str) -> dict:
    row = storage.get_settings(owner_id)
    if not row or not bool(row.get("onboarding_completed")):
        raise HTTPException(status_code=409, detail="请先完成首次设置")
    return row


def decorate_week(row: dict, settings: dict) -> dict:
    start = user_settings.coerce_date(row["week_start"])
    first = user_settings.coerce_date(settings["week_one_start"])
    version = int(row.get("version", 1))
    version_count = int(row.get("version_count", 1))
    label = f"第 {user_settings.week_number(start, first)} 周"
    if row.get("output_kind") == "custom" and row.get("template_name"):
        label += f" · {row['template_name']}"
    if version_count > 1 or version > 1:
        label += f" · 版本 {version}"
    return {
        **row,
        "week_end": user_settings.week_end(start).isoformat(),
        "week_number": user_settings.week_number(start, first),
        "display_label": label,
    }


def template_public(row: dict, *, include_definition: bool = False) -> dict:
    value = {
        "id": row["id"],
        "name": row["name"],
        "source_type": row["source_type"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_definition:
        value["definition"] = json.loads(row["definition_json"])
        value["analysis"] = json.loads(row.get("analysis_summary_json") or "{}")
        value["preview"] = template_system.placeholder_document(value["definition"])
    return value


@dataclass(frozen=True)
class QuotaReservation:
    identity: str
    usage_day: str
    headers: dict[str, str]


def consume_message_quota(request: Request) -> QuotaReservation:
    settings = app_settings(request)
    now = clock.now()
    usage_day = now.date().isoformat()
    reset_at = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), clock.TIMEZONE)
    retry_after = max(1, int((reset_at - now).total_seconds()))
    identity = visitor.rate_limit_key(request.state.client_ip)
    allowed, used = storage.consume_daily_message(identity, usage_day, settings.message_daily_limit)
    headers = {
        "X-RateLimit-Limit": str(settings.message_daily_limit),
        "X-RateLimit-Remaining": str(max(0, settings.message_daily_limit - used)),
        "X-RateLimit-Reset": str(int(reset_at.timestamp())),
    }
    if not allowed:
        headers["Retry-After"] = str(retry_after)
        raise HTTPException(
            status_code=429,
            detail=f"今天的 {settings.message_daily_limit} 条消息额度已用完，请明天再来",
            headers=headers,
        )
    return QuotaReservation(identity=identity, usage_day=usage_day, headers=headers)
