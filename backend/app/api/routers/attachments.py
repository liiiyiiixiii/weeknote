"""Attachment upload and speech-recognition endpoints."""

import asyncio

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, WebSocket
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from app import asr as asr_module
from app import attachments as attachment_service
from app import clock, runtime_store, storage, visitor
from app.api.common import require_settings

router = APIRouter(tags=["attachments"])


def _parse_slots(request: Request) -> asyncio.Semaphore:
    return request.app.state.attachment_parse_slots


@router.post("/api/attachments")
async def upload_attachment(
    request: Request,
    session_id: str = Form(...),
    file: UploadFile = File(...),
):
    owner_id = request.state.visitor_id
    owner_epoch = runtime_store.namespace_epoch(owner_id, "owner")
    require_settings(owner_id)
    try:
        async with _parse_slots(request):
            try:
                data = await file.read(attachment_service.MAX_FILE_SIZE + 1)
            finally:
                await file.close()
            if len(data) > attachment_service.MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="单个附件不能超过 16MB")
            return await run_in_threadpool(
                attachment_service.add,
                owner_id,
                session_id,
                file.filename or "",
                file.content_type or "",
                data,
                expected_owner_epoch=owner_epoch,
            )
    except attachment_service.AttachmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/attachments/{attachment_id}")
def delete_attachment(attachment_id: str, session_id: str, request: Request):
    removed = attachment_service.remove(request.state.visitor_id, session_id, attachment_id)
    if not removed:
        raise HTTPException(status_code=404, detail="附件不存在或已经失效")
    return {"ok": True}


@router.websocket("/ws/asr")
async def speech_recognition(websocket: WebSocket):
    if not visitor.websocket_origin_allowed(Headers(scope=websocket.scope)):
        await websocket.close(code=1008)
        return
    owner_id = websocket.scope["state"]["visitor_id"]
    user_config = storage.get_settings(owner_id)
    if not user_config or not bool(user_config.get("onboarding_completed")):
        await websocket.close(code=1008)
        return
    settings = websocket.scope["app"].state.settings
    now = clock.now()
    usage_day = now.date().isoformat()
    identity = visitor.rate_limit_key(websocket.scope["state"]["client_ip"])
    reserved_seconds = asr_module.MAX_AUDIO_SECONDS
    allowed, _used = storage.reserve_daily_asr(
        identity,
        usage_day,
        reserved_seconds,
        settings.asr_daily_seconds_limit,
    )
    if not allowed:
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "message": f"今天的语音额度已用完（每天 {settings.asr_daily_seconds_limit // 60} 分钟）",
            }
        )
        await websocket.close(code=1008)
        return
    audio_bytes = 0
    try:
        audio_bytes = await asr_module.handle_asr(websocket)
    finally:
        actual_seconds = min(
            reserved_seconds,
            (audio_bytes + asr_module.AUDIO_BYTES_PER_SECOND - 1) // asr_module.AUDIO_BYTES_PER_SECOND,
        )
        storage.release_daily_asr(identity, usage_day, reserved_seconds - actual_seconds)
