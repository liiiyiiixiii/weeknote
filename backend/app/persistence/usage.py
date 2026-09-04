"""Message and speech quota persistence interface."""

from app.persistence import storage_backend

consume_daily_message = storage_backend.consume_daily_message
reserve_daily_asr = storage_backend.reserve_daily_asr
release_daily_asr = storage_backend.release_daily_asr
