"""Saved weekly-report persistence interface."""

from app.persistence import storage_backend

create_week = storage_backend.create_week
list_weeks = storage_backend.list_weeks
get_week = storage_backend.get_week
delete_week = storage_backend.delete_week
delete_owner_data = storage_backend.delete_owner_data
earliest_week_start = storage_backend.earliest_week_start
