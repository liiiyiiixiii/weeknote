import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import attachments, clock, storage, user_settings, visitor

FAKE = {
    "report": {
        "title": "周报",
        "sections": [{"category": "工作", "items": [{"summary": "做了A", "detail": "细节"}]}],
    },
    "tech_summary": {"title": "技术", "topics": [{"topic": "T", "explanation": "说明"}]},
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.init_db()
    from app.main import app

    # Keep API tests hermetic: they must never depend on a developer's local
    # .env, while individual missing-key tests can override this explicitly.
    monkeypatch.setattr(
        app.state,
        "settings",
        replace(app.state.settings, deepseek_api_key="fake-key"),
    )
    return TestClient(app)


def _save_settings(client, week_one_start=None, **kwargs):
    current = user_settings.current_monday()
    payload = {
        "week_one_start": week_one_start or current.isoformat(),
        "purpose_mode": kwargs.get("purpose_mode", "default"),
        "custom_purpose_name": kwargs.get("custom_purpose_name", ""),
        "custom_purpose_description": kwargs.get("custom_purpose_description", ""),
        "detail_level": kwargs.get("detail_level", "standard"),
        "tone": kwargs.get("tone", "natural"),
    }
    return client.put("/api/settings", json=payload)


def _owner_id(client):
    client.get("/")
    signed = client.cookies.get(visitor.COOKIE_NAME)
    token = visitor._validate_cookie(signed)
    assert token
    return visitor.visitor_id(token)


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200


def test_health_endpoint_exposes_release_without_setup(client):
    from app import main as main_module

    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "release": main_module.APP_RELEASE}


def test_settings_defaults_and_save(client):
    current = user_settings.current_monday()
    r = client.get("/api/settings")
    data = r.json()
    assert r.status_code == 200
    assert data["configured"] is False
    assert data["defaults"]["week_one_start"] == current.isoformat()
    assert data["constraints"]["latest_week_one_end"] == (current + timedelta(days=6)).isoformat()
    assert data["current_week"]["display_label"] == "第 1 周"

    saved = _save_settings(client, (current + timedelta(days=2)).isoformat())
    assert saved.status_code == 200
    data = saved.json()
    assert data["configured"] is True
    assert data["settings"]["week_one_start"] == current.isoformat()
    assert data["current_week"]["display_label"] == "第 1 周"


def test_settings_defaults_use_earliest_history(client):
    current = user_settings.current_monday()
    earlier = current - timedelta(days=7)
    storage.create_week(_owner_id(client), earlier.isoformat(), "上一周的历史记录", "{}")

    r = client.get("/api/settings")
    data = r.json()
    assert data["configured"] is False
    assert data["defaults"]["week_one_start"] == earlier.isoformat()
    assert data["constraints"]["latest_week_one_start"] == earlier.isoformat()
    assert data["current_week"]["week_number"] == 2


def test_requires_settings_before_workflow(client):
    r = client.post("/api/organize", json={"raw_input": "本周我做了A，用到了T技术，细节是这样。"})
    assert r.status_code == 409
    r2 = client.post("/api/chat", json={"session_id": "s", "message": "hi"})
    assert r2.status_code == 409


def test_organize_and_export(client, monkeypatch):
    from app import organize as org_module

    current = user_settings.current_monday()
    saved = _save_settings(client, (current + timedelta(days=2)).isoformat())
    assert saved.status_code == 200

    monkeypatch.setattr(org_module, "organize", lambda *a, **k: FAKE)

    r = client.post("/api/organize", json={"raw_input": "本周我做了A，用到了T技术，细节是这样。"})
    assert r.status_code == 200
    data = r.json()
    assert data["organized"]["report"]["title"].startswith("第 1 周工作汇报")
    assert data["organized"]["tech_summary"]["title"].startswith("第 1 周技术总结")
    week_id = data["week_id"]

    r3 = client.get("/api/weeks")
    weeks = r3.json()
    assert weeks[0]["id"] == week_id
    assert weeks[0]["display_label"] == "第 1 周"
    assert weeks[0]["week_end"] == (current + timedelta(days=6)).isoformat()

    r4 = client.get(f"/api/weeks/{week_id}")
    week = r4.json()
    assert week["display_label"] == "第 1 周"
    assert week["week_number"] == 1
    assert week["report"]["report"]["title"].startswith("第 1 周工作汇报")

    r2 = client.get(f"/api/weeks/{week_id}/export?doc=report")
    assert r2.status_code == 200
    assert "wordprocessingml" in r2.headers["content-type"]
    assert r2.content[:2] == b"PK"  # docx 是 zip 容器


def test_organize_too_short(client):
    _save_settings(client)
    r = client.post("/api/organize", json={"raw_input": "hi"})
    assert r.status_code == 400


def test_settings_validation_blocks_invalid_ranges(client):
    current = user_settings.current_monday()
    future = client.put(
        "/api/settings",
        json={
            "week_one_start": (current + timedelta(days=7)).isoformat(),
            "purpose_mode": "default",
            "custom_purpose_name": "",
            "custom_purpose_description": "",
            "detail_level": "standard",
            "tone": "natural",
        },
    )
    assert future.status_code == 400

    earlier = current - timedelta(days=7)
    storage.create_week(_owner_id(client), earlier.isoformat(), "上一周的历史记录", "{}")
    blocked = client.put(
        "/api/settings",
        json={
            "week_one_start": current.isoformat(),
            "purpose_mode": "default",
            "custom_purpose_name": "",
            "custom_purpose_description": "",
            "detail_level": "standard",
            "tone": "natural",
        },
    )
    assert blocked.status_code == 400


def test_week_context():
    from app import main as m

    info = m._week_info()
    assert info["monday"] <= info["today"] <= info["sunday"]
    ctx = m._week_context(info)
    assert ctx.startswith("今天是")
    assert "日期区间为" in ctx
    assert str(info["week_number"]) in ctx


def test_daily_message_limit_is_enforced_atomically(client, monkeypatch):
    from app import main as main_module
    from app import organize as org_module

    _save_settings(client)
    monkeypatch.setattr(
        main_module.app.state,
        "settings",
        replace(main_module.app.state.settings, message_daily_limit=2),
    )
    monkeypatch.setattr(org_module, "organize", lambda *a, **k: FAKE)

    payload = {"raw_input": "本周完成了接口安全加固和测试验证工作。"}
    assert client.post("/api/organize", json=payload).status_code == 200
    second = client.post("/api/organize", json=payload)
    assert second.status_code == 200
    assert second.headers["x-ratelimit-remaining"] == "0"

    blocked = client.post("/api/organize", json=payload)
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"]


def test_chat_limit_returns_frontend_quota_contract(client, monkeypatch):
    from app import main as main_module

    _save_settings(client)
    monkeypatch.setattr(
        main_module.app.state,
        "settings",
        replace(
            main_module.app.state.settings,
            message_daily_limit=2,
            deepseek_api_key="fake-key",
        ),
    )

    def fake_stream(*args, **kwargs):
        yield {"type": "delta", "text": "收到。"}
        yield {"type": "done"}

    monkeypatch.setattr(main_module.agent, "stream_chat", fake_stream)
    payload = {"session_id": "quota-chat", "message": "本周完成了接口测试。", "mode": "normal"}

    first = client.post("/api/chat", json=payload)
    second = client.post("/api/chat", json=payload)
    blocked = client.post("/api/chat", json=payload)

    assert first.status_code == 200
    assert first.headers["x-ratelimit-limit"] == "2"
    assert first.headers["x-ratelimit-remaining"] == "1"
    assert second.status_code == 200
    assert second.headers["x-ratelimit-remaining"] == "0"
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "今天的 2 条消息额度已用完，请明天再来"
    assert blocked.headers["x-ratelimit-limit"] == "2"
    assert blocked.headers["x-ratelimit-remaining"] == "0"
    assert int(blocked.headers["x-ratelimit-reset"]) > 0
    assert int(blocked.headers["retry-after"]) > 0


def test_visitors_cannot_read_each_others_history(client, monkeypatch):
    from app import organize as org_module

    _save_settings(client)
    monkeypatch.setattr(org_module, "organize", lambda *a, **k: FAKE)
    created = client.post("/api/organize", json={"raw_input": "本周完成了匿名访客之间的数据隔离验证。"})
    week_id = created.json()["week_id"]

    stranger = TestClient(client.app)
    assert _save_settings(stranger).status_code == 200
    assert stranger.get(f"/api/weeks/{week_id}").status_code == 404


def test_same_week_api_keeps_both_versions(client, monkeypatch):
    from app import organize as org_module

    _save_settings(client)
    monkeypatch.setattr(org_module, "organize", lambda *a, **k: FAKE)

    first = client.post("/api/organize", json={"raw_input": "本周完成了第一个不会被覆盖的版本。"})
    second = client.post("/api/organize", json={"raw_input": "本周完成了第二个需要独立保留的版本。"})
    assert first.status_code == second.status_code == 200

    weeks = client.get("/api/weeks").json()
    assert [week["version"] for week in weeks] == [2, 1]
    assert weeks[0]["display_label"].endswith("版本 2")
    assert weeks[1]["display_label"].endswith("版本 1")
    first_record = client.get(f"/api/weeks/{first.json()['week_id']}").json()
    assert "第一个" in first_record["raw_input"]

    assert client.delete(f"/api/weeks/{first.json()['week_id']}").status_code == 200
    remaining = client.get("/api/weeks").json()
    assert len(remaining) == 1
    assert remaining[0]["display_label"].endswith("版本 2")


def test_privacy_endpoint_and_delete_all_data(client):
    _save_settings(client)
    owner_id = _owner_id(client)
    storage.create_week(owner_id, user_settings.current_monday().isoformat(), "content", "{}")

    privacy = client.get("/api/privacy")
    assert privacy.status_code == 200
    assert privacy.json()["runtime_state_persisted"] is True
    assert privacy.json()["raw_attachment_files_persisted"] is False
    assert privacy.json()["attachments_persisted"] is True
    assert privacy.json()["template_samples_persisted"] is True
    assert privacy.json()["timezone"] == clock.TIMEZONE_NAME

    deleted = client.delete("/api/data")
    assert deleted.status_code == 200
    assert deleted.json()["removed"] == {"weeks": 1, "templates": 0, "settings": 1}
    assert storage.list_weeks(owner_id) == []
    assert storage.get_settings(owner_id) is None


def test_delete_all_data_wins_against_inflight_organize(client, monkeypatch):
    """A request that read settings before erasure cannot recreate a report later."""
    from app import organize as org_module

    assert _save_settings(client).status_code == 200
    owner_id = _owner_id(client)
    entered = threading.Event()
    release = threading.Event()

    def blocked_organize(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return FAKE

    monkeypatch.setattr(org_module, "organize", blocked_organize)
    worker = TestClient(client.app)
    worker.cookies.set(visitor.COOKIE_NAME, client.cookies.get(visitor.COOKIE_NAME))
    payload = {"raw_input": "本周完成了隐私删除并发保护的回归测试。"}

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker.post, "/api/organize", json=payload)
        assert entered.wait(timeout=5)
        deleted = client.delete("/api/data")
        release.set()
        organized = future.result(timeout=5)

    assert deleted.status_code == 200
    assert organized.status_code == 409
    assert storage.list_weeks(owner_id) == []
    assert storage.get_settings(owner_id) is None


def test_attachment_admission_rejects_when_bounded_queue_is_full():
    from app.main import AttachmentAdmissionMiddleware

    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()

        async def downstream(scope, receive, send):
            entered.set()
            await release.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = AttachmentAdmissionMiddleware(downstream, limit=1)
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/attachments",
            "raw_path": b"/api/attachments",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        }

        async def call():
            sent = []

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                sent.append(message)

            await middleware(dict(scope), receive, send)
            return sent

        first = asyncio.create_task(call())
        await entered.wait()
        rejected = await call()
        release.set()
        completed = await first
        return completed, rejected

    completed, rejected = asyncio.run(scenario())
    assert completed[0]["status"] == 200
    assert rejected[0]["status"] == 503
    assert (b"retry-after", b"2") in rejected[0]["headers"]


def test_week_info_uses_application_clock(monkeypatch):
    from app import main as main_module

    monkeypatch.setattr(clock, "today", lambda: date(2026, 8, 24))
    info = main_module._week_info()
    assert info["today"] == date(2026, 8, 24)
    assert info["monday"] == date(2026, 8, 24)
    assert user_settings.current_monday() == date(2026, 8, 24)


def test_attachment_parser_runs_outside_event_loop_thread(client, monkeypatch):
    caller_thread = threading.get_ident()
    parser_threads = []

    def fake_add(owner_id, session_id, filename, content_type, data, **kwargs):
        parser_threads.append(threading.get_ident())
        return {
            "id": "attachment",
            "name": filename,
            "size": len(data),
            "content_type": content_type,
            "category": "文本",
            "summary": "ok",
            "char_count": len(data),
            "truncated": False,
        }

    _save_settings(client)
    monkeypatch.setattr(attachments, "add", fake_add)
    response = client.post(
        "/api/attachments",
        data={"session_id": "session-1"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 200
    assert parser_threads and parser_threads[0] != caller_thread
