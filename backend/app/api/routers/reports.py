"""Saved report, export, and privacy endpoints."""

import io
import json
import re
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response

from app import agent, attachments, clock, docx_render, runtime_store, storage, template_system, user_settings
from app.api.common import app_settings, decorate_week, require_settings

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/weeks")
def list_weeks(request: Request):
    owner_id = request.state.visitor_id
    settings = require_settings(owner_id)
    return [decorate_week(row, settings) for row in storage.list_weeks(owner_id)]


@router.get("/weeks/{week_id}")
def get_week(week_id: int, request: Request):
    owner_id = request.state.visitor_id
    settings = require_settings(owner_id)
    row = storage.get_week(owner_id, week_id)
    if not row:
        raise HTTPException(status_code=404, detail="周记录不存在")
    decorated = decorate_week(row, settings)
    data = json.loads(row["report_json"])
    output_kind = row.get("output_kind") or "weekly"
    response = {
        "id": row["id"],
        **decorated,
        "raw_input": row["raw_input"],
        "output_kind": output_kind,
        "template_name": row.get("template_name") or "",
        "updated_at": row["updated_at"],
    }
    if output_kind == "custom":
        response["definition"] = json.loads(row.get("template_definition_json") or "{}")
        response["document"] = data
    else:
        response["report"] = user_settings.apply_titles(
            data,
            user_settings.coerce_date(row["week_start"]),
            user_settings.coerce_date(settings["week_one_start"]),
        )
    return response


@router.get("/weeks/{week_id}/export")
def export_week(week_id: int, request: Request, doc: str = "report"):
    owner_id = request.state.visitor_id
    settings = require_settings(owner_id)
    row = storage.get_week(owner_id, week_id)
    if not row:
        raise HTTPException(status_code=404, detail="周记录不存在")
    data = json.loads(row["report_json"])
    version_suffix = (
        f"_v{row['version']}" if int(row.get("version_count", 1)) > 1 or int(row.get("version", 1)) > 1 else ""
    )
    if (row.get("output_kind") or "weekly") == "custom":
        definition = json.loads(row.get("template_definition_json") or "{}")
        document = docx_render.render_custom(definition, data)
        safe_name = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", row.get("template_name") or "自定义汇报")
        filename = f"{safe_name}_{row['week_start']}{version_suffix}.docx"
    else:
        data = user_settings.apply_titles(
            data,
            user_settings.coerce_date(row["week_start"]),
            user_settings.coerce_date(settings["week_one_start"]),
        )
        if doc == "tech":
            document = docx_render.render_tech(data)
            filename = f"技术总结_{row['week_start']}{version_suffix}.docx"
        else:
            document = docx_render.render_report(data)
            filename = f"工作汇报_{row['week_start']}{version_suffix}.docx"
    buffer = io.BytesIO()
    document.save(buffer)
    buffer.seek(0)
    encoded = quote(filename)
    return Response(
        content=buffer.read(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.delete("/weeks/{week_id}")
def delete_week(week_id: int, request: Request):
    if not storage.delete_week(request.state.visitor_id, week_id):
        raise HTTPException(status_code=404, detail="周记录不存在")
    return {"ok": True}


@router.delete("/data")
def delete_all_data(request: Request):
    removed, runtime_removed = runtime_store.delete_all_owner_data(request.state.visitor_id)
    return {"ok": True, "removed": removed, "runtime_removed": runtime_removed}


@router.get("/privacy")
def privacy(request: Request):
    settings = app_settings(request)
    return {
        "report_retention_days": settings.report_retention_days,
        "usage_retention_days": settings.usage_retention_days,
        "runtime_state_persisted": True,
        "raw_attachment_files_persisted": False,
        "attachments_persisted": True,
        "template_samples_persisted": True,
        "attachment_ttl_seconds": attachments.ATTACHMENT_TTL_SECONDS,
        "conversation_ttl_seconds": agent.CONVERSATION_TTL_SECONDS,
        "template_draft_ttl_seconds": template_system.DRAFT_TTL_SECONDS,
        "timezone": clock.TIMEZONE_NAME,
        "processors": [
            {"name": "DeepSeek", "purpose": "文本整理与模板分析"},
            {"name": "火山引擎", "purpose": "实时语音识别"},
        ],
    }
