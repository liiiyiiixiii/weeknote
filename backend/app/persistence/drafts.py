"""Template-draft runtime-state persistence interface."""

from app.persistence import runtime_backend

insert_draft = runtime_backend.insert_draft
load_draft = runtime_backend.load_draft
update_draft = runtime_backend.update_draft
discard_draft = runtime_backend.discard_draft
clear_owner_drafts = runtime_backend.clear_owner_drafts
cleanup_drafts = runtime_backend.cleanup_drafts
