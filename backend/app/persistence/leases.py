"""Cross-process runtime lease interface."""

from app.persistence import runtime_backend

SessionLease = runtime_backend.SessionLease
session_lease = runtime_backend.session_lease
