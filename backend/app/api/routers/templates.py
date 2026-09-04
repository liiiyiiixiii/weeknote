"""Custom report template and template-draft endpoints."""

import json
import logging

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app import agent, attachments, runtime_store, storage, template_system
from app.api.common import (
    app_settings,
    consume_message_quota,
    require_settings,
    sse,
    template_public,
)
from app.schemas import (
    TemplateAnalyzeRequest,
    TemplateDraftChatRequest,
    TemplateDraftCreateRequest,
    TemplateDraftUpdateRequest,
    TemplateRenameRequest,
    TemplateSaveRequest,
    TemplateSelectionRequest,
)

router = APIRouter(tags=["templates"])
logger = logging.getLogger(__name__)


@router.get("/api/templates")
def list_templates(request: Request):
    owner_id = request.state.visitor_id
    settings = require_settings(owner_id)
    rows = storage.list_templates(owner_id)
    return {
        "selected_template_id": settings.get("selected_template_id"),
        "templates": [template_public(row) for row in rows if row["status"] == "active"],
        "drafts": [template_public(row) for row in rows if row["status"] == "draft"],
        "limit": 20,
    }


@router.get("/api/templates/{template_id}")
def get_template(template_id: int, request: Request):
    require_settings(request.state.visitor_id)
    row = storage.get_template(request.state.visitor_id, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="模板不存在")
    return template_public(row, include_definition=True)


@router.post("/api/template-drafts")
def create_template_draft(req: TemplateDraftCreateRequest, request: Request):
    del req
    owner_id = request.state.visitor_id
    owner_epoch = runtime_store.namespace_epoch(owner_id, "owner")
    require_settings(owner_id)
    try:
        return template_system.public_draft(
            template_system.create_manual_draft(owner_id, expected_owner_epoch=owner_epoch)
        )
    except template_system.DraftCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except template_system.DraftConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/templates/{template_id}/edit-draft")
def create_edit_draft(template_id: int, request: Request):
    owner_id = request.state.visitor_id
    owner_epoch = runtime_store.namespace_epoch(owner_id, "owner")
    require_settings(owner_id)
    row = storage.get_template(owner_id, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="模板不存在")
    try:
        return template_system.public_draft(
            template_system.create_edit_draft(owner_id, row, expected_owner_epoch=owner_epoch)
        )
    except template_system.DraftCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except template_system.DraftConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/api/template-drafts/{draft_id}")
def update_template_draft(draft_id: str, req: TemplateDraftUpdateRequest, request: Request):
    require_settings(request.state.visitor_id)
    try:
        draft = template_system.update_draft(
            request.state.visitor_id,
            draft_id,
            req.definition.model_dump(),
            req.base_revision,
        )
    except template_system.DraftConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not draft:
        raise HTTPException(status_code=404, detail="模板草稿不存在或已经失效")
    return template_system.public_draft(draft)


@router.delete("/api/template-drafts/{draft_id}")
def delete_template_draft(draft_id: str, request: Request):
    require_settings(request.state.visitor_id)
    draft = template_system.discard_draft(request.state.visitor_id, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="模板草稿不存在或已经失效")
    if draft.attachment_session_id:
        attachments.clear_session(request.state.visitor_id, draft.attachment_session_id)
    return {"ok": True}


@router.post("/api/template-drafts/analyze")
def analyze_template_samples(req: TemplateAnalyzeRequest, request: Request, response: Response):
    owner_id = request.state.visitor_id
    owner_epoch = runtime_store.namespace_epoch(owner_id, "owner")
    require_settings(owner_id)
    settings = app_settings(request)
    if not settings.deepseek_api_key:
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用")
    quota = consume_message_quota(request)
    response.headers.update(quota.headers)
    try:
        return template_system.analyze_samples(
            owner_id,
            req.session_id,
            req.attachment_ids,
            settings.deepseek_api_key,
            settings.deepseek_base_url,
            settings.deepseek_model,
            owner_epoch,
        )
    except attachments.AttachmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except template_system.DraftCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except template_system.DraftConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, ValidationError) as exc:
        logger.warning("模板样例分析失败: %s", exc)
        raise HTTPException(status_code=502, detail="模板分析结果无法校验，请调整样例后重试") from exc
    except Exception as exc:
        logger.warning("模板样例分析请求失败: %s", exc)
        raise HTTPException(status_code=502, detail="模板分析失败，请稍后重试") from exc


@router.post("/api/template-drafts/{draft_id}/chat")
def chat_with_template_draft(draft_id: str, req: TemplateDraftChatRequest, request: Request):
    owner_id = request.state.visitor_id
    owner_epoch = runtime_store.namespace_epoch(owner_id, "owner")
    require_settings(owner_id)
    if not template_system.get_draft(owner_id, draft_id):
        raise HTTPException(status_code=404, detail="模板草稿不存在或已经失效")
    settings = app_settings(request)
    if not settings.deepseek_api_key:
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用")
    quota = consume_message_quota(request)

    def generate():
        try:
            message, draft = template_system.revise_draft_with_ai(
                owner_id,
                draft_id,
                req.message,
                settings.deepseek_api_key,
                settings.deepseek_base_url,
                settings.deepseek_model,
                req.base_revision,
                owner_epoch,
            )
            yield sse({"type": "delta", "text": message})
            yield sse({"type": "template", "draft": template_system.public_draft(draft)})
        except LookupError as exc:
            yield sse({"type": "error", "message": str(exc)})
        except template_system.DraftConflictError as exc:
            yield sse({"type": "error", "code": "draft_conflict", "message": str(exc)})
        except Exception as exc:
            logger.warning("模板 AI 修改失败: %s", exc)
            yield sse({"type": "error", "message": "AI 修改模板失败，请稍后重试"})
        yield sse({"type": "done"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            **quota.headers,
        },
    )


def _finish_template_save(
    owner_id: str,
    draft,
    name: str,
    *,
    expected_draft_revision: int,
    template_id: int | None = None,
):
    if draft.revision != expected_draft_revision:
        raise HTTPException(status_code=409, detail="模板草稿已在其他页面或请求中更新，请重新确认后保存")
    name = template_system.validate_name(name)
    definition_json = json.dumps(draft.definition, ensure_ascii=False)
    runtime_args = {
        "runtime_draft_id": draft.id,
        "expected_draft_revision": expected_draft_revision,
        "expected_runtime_epoch": draft.runtime_epoch,
    }
    try:
        if template_id is None:
            if draft.source_template_id is not None:
                raise HTTPException(status_code=409, detail="该草稿用于编辑现有模板")
            row = storage.create_template(
                owner_id,
                name,
                draft.source_type,
                definition_json,
                json.dumps(draft.analysis, ensure_ascii=False),
                **runtime_args,
            )
        else:
            if int(draft.source_template_id or 0) != int(template_id):
                raise HTTPException(status_code=400, detail="模板草稿与目标模板不匹配")
            source_revision = int(draft.source_template_revision or 0)
            if source_revision < 1:
                raise HTTPException(status_code=409, detail="模板版本已失效，请重新打开后编辑")
            if draft.source_template_status == "draft":
                row = storage.activate_legacy_template(
                    owner_id,
                    template_id,
                    name,
                    definition_json,
                    expected_revision=source_revision,
                    **runtime_args,
                )
            else:
                row = storage.update_template(
                    owner_id,
                    template_id,
                    name,
                    definition_json,
                    expected_revision=source_revision,
                    **runtime_args,
                )
            if not row:
                if storage.get_template(owner_id, template_id):
                    raise HTTPException(status_code=409, detail="模板已被其他页面更新，请重新打开后再保存")
                raise HTTPException(status_code=404, detail="模板不存在")
    except storage.RuntimeStateConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    storage.save_template_selection(owner_id, int(row["id"]))
    if draft.attachment_session_id:
        attachments.clear_session(owner_id, draft.attachment_session_id)
    return template_public(row, include_definition=True)


@router.post("/api/templates")
def create_template(req: TemplateSaveRequest, request: Request):
    owner_id = request.state.visitor_id
    require_settings(owner_id)
    draft = template_system.get_draft(owner_id, req.draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="模板草稿不存在或已经失效")
    try:
        return _finish_template_save(
            owner_id,
            draft,
            req.name,
            expected_draft_revision=req.draft_revision,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/templates/{template_id}")
def update_template(template_id: int, req: TemplateSaveRequest, request: Request):
    owner_id = request.state.visitor_id
    require_settings(owner_id)
    draft = template_system.get_draft(owner_id, req.draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="模板草稿不存在或已经失效")
    try:
        return _finish_template_save(
            owner_id,
            draft,
            req.name,
            expected_draft_revision=req.draft_revision,
            template_id=template_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/api/templates/{template_id}")
def rename_template(template_id: int, req: TemplateRenameRequest, request: Request):
    owner_id = request.state.visitor_id
    require_settings(owner_id)
    try:
        row = storage.rename_template(owner_id, template_id, template_system.validate_name(req.name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="模板不存在")
    return template_public(row, include_definition=True)


@router.delete("/api/templates/{template_id}")
def delete_template(template_id: int, request: Request):
    owner_id = request.state.visitor_id
    require_settings(owner_id)
    if not storage.delete_template(owner_id, template_id):
        raise HTTPException(status_code=404, detail="模板不存在")
    template_system.clear_custom_conversations(owner_id)
    return {"ok": True, "selected_template_id": None}


@router.put("/api/settings/template-selection")
def select_template(req: TemplateSelectionRequest, request: Request):
    owner_id = request.state.visitor_id
    require_settings(owner_id)
    saved = storage.save_template_selection(owner_id, req.template_id)
    if not saved:
        raise HTTPException(status_code=404, detail="自定义模板不存在")
    agent.clear_conversations(owner_id)
    template_system.clear_custom_conversations(owner_id)
    return {"selected_template_id": saved.get("selected_template_id")}
