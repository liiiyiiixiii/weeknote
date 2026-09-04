"""Database initialization and maintenance interface."""

from app.persistence import storage_backend

init_db = storage_backend.init_db
cleanup_expired = storage_backend.cleanup_expired
legacy_attachment_context_count = storage_backend.legacy_attachment_context_count
scrub_legacy_attachment_contexts = storage_backend.scrub_legacy_attachment_contexts
