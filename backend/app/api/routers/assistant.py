"""AI conversation and one-shot report organization endpoints."""

import json
import logging

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app import agent, attachments, organize, runtime_store, storage, template_system, user_settings
from app.api.common import (
    app_settings,
    consume_message_quota,
    require_settings,
    sse,
    week_context,
    week_info,
)
from app.schemas import ChatRequest, Organized, OrganizeRequest

router = APIRouter(prefix="/api", tags=["assistant"])
logger = logging.getLogger(__name__)


@router.post("/chat")
def chat(req: ChatRequest, request: Request):
    owner_id = request.state.visitor_id
    owner_epoch = runtime_store.namespace_epoch(owner_id, "owner")
    user_config = require_settings(owner_id)
    date_context = week_context(week_info(user_config), user_config)
    try:
        attachment_context = attachments.context_for(owner_id, req.session_id, req.attachment_ids)
    except attachments.AttachmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not req.message.strip() and not attachment_context.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")
    settings = app_settings(request)
    if not settings.deepseek_api_key:
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用")
    template_row = None
    if req.template_id is not None:
        template_row = storage.get_template(owner_id, req.template_id, active_only=True)
        if not template_row:
            raise HTTPException(status_code=404, detail="自定义模板不存在")
    quota = consume_message_quota(request)
    try:
        bound = template_system.bind_session_template(
            owner_id,
            req.session_id,
            req.template_id,
            expected_owner_epoch=owner_epoch,
        )
    except runtime_store.RuntimeOwnerClearedError as exc:
        raise HTTPException(status_code=409, detail="当前会话已被清除，请开始新记录") from exc
    if not bound:
        raise HTTPException(status_code=409, detail="同一会话不能中途切换模板，请开始新记录")

    def generate():
        stream = (
            template_system.stream_custom_chat(
                owner_id,
                req.session_id,
                template_row,
                req.message,
                settings.deepseek_api_key,
                settings.deepseek_base_url,
                settings.deepseek_model,
                date_context=date_context,
                settings=user_config,
                attachment_context=attachment_context,
                expected_owner_epoch=owner_epoch,
            )
            if template_row
            else agent.stream_chat(
                owner_id,
                req.session_id,
                req.message,
                settings.deepseek_api_key,
                settings.deepseek_base_url,
                settings.deepseek_model,
                date_context=date_context,
                settings=user_config,
                attachment_context=attachment_context,
                mode=req.mode,
                expected_owner_epoch=owner_epoch,
            )
        )
        for event in stream:
            if event.get("type") == "final":
                attachments.clear_session(owner_id, req.session_id)
            yield sse(event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            **quota.headers,
        },
    )


@router.post("/organize")
def organize_notes(req: OrganizeRequest, request: Request, response: Response):
    owner_id = request.state.visitor_id
    owner_epoch = runtime_store.namespace_epoch(owner_id, "owner")
    user_config = require_settings(owner_id)
    raw = req.raw_input.strip()
    if len(raw) < 10:
        raise HTTPException(status_code=400, detail="输入太短，请至少输入 10 个字")
    info = week_info(user_config)
    date_context = week_context(info, user_config)
    settings = app_settings(request)
    if not settings.deepseek_api_key:
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用")
    quota = consume_message_quota(request)
    response.headers.update(quota.headers)
    try:
        result = organize.organize(
            raw,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            date_context=date_context,
            settings=user_config,
        )
    except Exception as exc:
        logger.warning("整理请求失败: %s", exc)
        raise HTTPException(status_code=502, detail="整理失败，请稍后重试") from exc
    try:
        validated = Organized.model_validate(result).model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail=f"结果校验失败：{exc}") from exc
    week_start = info["monday"]
    first_start = user_settings.coerce_date(user_config["week_one_start"])
    validated = user_settings.apply_titles(validated, week_start, first_start)
    try:
        week_id = storage.create_week(
            owner_id,
            week_start.isoformat(),
            raw,
            json.dumps(validated, ensure_ascii=False),
            expected_owner_epoch=owner_epoch,
        )
    except storage.RuntimeStateConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"week_id": week_id, "organized": validated}
