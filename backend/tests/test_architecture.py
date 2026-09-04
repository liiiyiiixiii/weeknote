"""Regression tests for the public application and persistence boundaries."""

from app import runtime_store, storage
from app.core.config import AppSettings
from app.main import create_app
from app.persistence import attachments, database, drafts, leases, reports, sessions, templates, usage


def test_app_settings_apply_safe_bounds_and_defaults():
    settings = AppSettings.from_env(
        {
            "APP_ENV": "production",
            "APP_TIMEZONE": "UTC",
            "ASR_MAX_SECONDS": "45",
            "ATTACHMENT_PARSE_CONCURRENCY": "99",
            "ATTACHMENT_UPLOAD_ADMISSION": "1",
            "MESSAGE_DAILY_LIMIT": "0",
            "ASR_DAILY_SECONDS_LIMIT": "999999",
            "ALLOWED_HOSTS": "example.com, localhost",
        }
    )

    assert settings.release == "0.1.0"
    assert settings.app_env == "production"
    assert settings.app_timezone == "UTC"
    assert settings.asr_max_seconds == 45
    assert settings.message_daily_limit == 1
    assert settings.asr_daily_seconds_limit == 86_400
    assert settings.attachment_parse_concurrency == 8
    assert settings.attachment_upload_admission == 8
    assert settings.allowed_hosts == ("example.com", "localhost")


def test_app_factory_preserves_public_route_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "factory.db")
    application = create_app(AppSettings.from_env({"ALLOWED_HOSTS": "*"}))
    all_routes = list(application.routes)
    for route in application.routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            all_routes.extend(included.routes)
    routes = {(route.path, method) for route in all_routes for method in getattr(route, "methods", set())}

    expected = {
        ("/", "GET"),
        ("/api/health", "GET"),
        ("/api/settings", "GET"),
        ("/api/settings", "PUT"),
        ("/api/chat", "POST"),
        ("/api/organize", "POST"),
        ("/api/attachments", "POST"),
        ("/api/templates", "GET"),
        ("/api/weeks", "GET"),
        ("/api/privacy", "GET"),
    }
    assert expected <= routes
    assert any(getattr(route, "path", None) == "/ws/asr" for route in all_routes)


def test_persistence_interfaces_delegate_without_behavior_changes():
    assert database.init_db is storage.init_db
    assert reports.create_week is storage.create_week
    assert reports.get_week is storage.get_week
    assert templates.save_settings is storage.save_settings
    assert templates.create_template is storage.create_template
    assert usage.consume_daily_message is storage.consume_daily_message
    assert usage.reserve_daily_asr is storage.reserve_daily_asr

    assert sessions.load_conversation is runtime_store.load_conversation
    assert sessions.bind_session_template is runtime_store.bind_session_template
    assert attachments.insert_attachment is runtime_store.insert_attachment
    assert drafts.update_draft is runtime_store.update_draft
    assert leases.session_lease is runtime_store.session_lease
