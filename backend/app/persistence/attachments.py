"""Attachment runtime-state persistence interface."""

from app.persistence import runtime_backend

prepare_attachment = runtime_backend.prepare_attachment
insert_attachment = runtime_backend.insert_attachment
load_attachments = runtime_backend.load_attachments
remove_attachment = runtime_backend.remove_attachment
clear_owner_attachments = runtime_backend.clear_owner_attachments
clear_session_attachments = runtime_backend.clear_session_attachments
cleanup_attachments = runtime_backend.cleanup_attachments
