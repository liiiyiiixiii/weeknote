"""Visitor settings endpoints."""

from fastapi import APIRouter, HTTPException, Request

from app import agent, runtime_store, storage, template_system, user_settings
from app.api.common import settings_public
from app.schemas import SettingsRequest

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(request: Request):
    owner_id = request.state.visitor_id
    return settings_public(owner_id, storage.get_settings(owner_id))


@router.put("")
def save_settings(req: SettingsRequest, request: Request):
    owner_id = request.state.visitor_id
    owner_epoch = runtime_store.namespace_epoch(owner_id, "owner")
    earliest = storage.earliest_week_start(owner_id)
    try:
        payload = req.model_dump()
        payload.update(
            {
                "purpose_mode": "default",
                "custom_purpose_name": "",
                "custom_purpose_description": "",
            }
        )
        values = user_settings.validate_settings(payload, earliest)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        saved = storage.save_settings(owner_id, values, expected_owner_epoch=owner_epoch)
    except storage.RuntimeStateConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    agent.clear_conversations(owner_id)
    template_system.clear_custom_conversations(owner_id)
    return settings_public(owner_id, saved)
