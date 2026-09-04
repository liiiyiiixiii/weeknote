import json

import pytest

from app import agent, runtime_store, storage, user_settings


@pytest.fixture(autouse=True)
def isolated_runtime_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "agent.db")
    storage.init_db()
    yield


def test_extract_final_json():
    text = """好的，已经整理好了。
<<<SUMMARY>>>
{"report": {"title": "周报", "sections": []}, "tech_summary": {"title": "技术", "topics": []}}"""
    result = agent.extract_final_json(text)
    assert result is not None
    assert result["report"]["title"] == "周报"
    assert result["tech_summary"]["topics"] == []


def test_extract_final_json_returns_none_without_marker():
    assert agent.extract_final_json("请问你周三做了什么？") is None


def test_mode_profiles_use_real_thinking_switches():
    normal = agent._mode_request_options("normal")
    advanced = agent._mode_request_options("advanced")

    assert normal == {
        "temperature": 0.3,
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    assert advanced == {
        "reasoning_effort": "high",
        "extra_body": {"thinking": {"type": "enabled"}},
    }
    assert "不输出「思路摘要」" in agent._mode_context("normal")
    assert "2～4 条" in agent._mode_context("advanced")
    assert "最终周报的篇幅" in agent._mode_context("normal")
    assert "最终周报的篇幅" in agent._mode_context("advanced")


def test_advanced_stream_discards_raw_reasoning_and_switches_mode(monkeypatch):
    agent.clear_conversations()
    calls = []
    replies = iter(
        [
            [(None, "不能展示的内部推理"), ("普通回复。", None)],
            [(None, "另一段内部推理"), ("思路摘要：\n- 已核对事项\n- 还缺结果\n\n请补充结果。", None)],
        ]
    )

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            chunks = []
            for content, reasoning in next(replies):
                delta = type(
                    "Delta",
                    (),
                    {"content": content, "reasoning_content": reasoning},
                )()
                chunks.append(type("Chunk", (), {"choices": [type("Choice", (), {"delta": delta})()]})())
            return chunks

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": Completions()})()

    monkeypatch.setattr(agent, "OpenAI", FakeOpenAI)

    normal_events = list(
        agent.stream_chat("owner", "mode-switch", "第一条", "key", "https://example.invalid", "model", mode="normal")
    )
    advanced_events = list(
        agent.stream_chat("owner", "mode-switch", "第二条", "key", "https://example.invalid", "model", mode="advanced")
    )

    normal_text = "".join(event.get("text", "") for event in normal_events)
    advanced_text = "".join(event.get("text", "") for event in advanced_events)
    assert normal_text == "普通回复。"
    assert "思路摘要" in advanced_text
    assert "不能展示的内部推理" not in normal_text
    assert "另一段内部推理" not in advanced_text
    assert calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert calls[0]["temperature"] == 0.3
    assert "reasoning_effort" not in calls[0]
    assert calls[1]["extra_body"] == {"thinking": {"type": "enabled"}}
    assert calls[1]["reasoning_effort"] == "high"
    assert "temperature" not in calls[1]

    snapshot = runtime_store.load_conversation(
        "owner",
        "mode-switch",
        now=agent.time.time(),
        ttl_seconds=agent.CONVERSATION_TTL_SECONDS,
    )
    assert snapshot
    history = snapshot.data["messages"]
    assert history[0]["mode"] == "advanced"
    assert "高级（深入模式）" in history[0]["content"]
    assert all("内部推理" not in message.get("content", "") for message in history)


def test_finalized_chat_never_persists_attachment_context(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.init_db()
    agent.clear_conversations()

    final = {
        "report": {
            "title": "周报",
            "sections": [
                {
                    "category": "工作",
                    "items": [{"summary": "完成接口", "detail": "完成实现"}],
                }
            ],
        },
        "tech_summary": {"title": "技术", "topics": []},
    }
    output = "好的，已经整理好了。\n<<<SUMMARY>>>\n" + json.dumps(final, ensure_ascii=False)

    class Chunk:
        choices = [type("Choice", (), {"delta": type("Delta", (), {"content": output})()})()]

    class Completions:
        def create(self, **kwargs):
            return [Chunk()]

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": Completions()})()

    monkeypatch.setattr(agent, "OpenAI", FakeOpenAI)
    current = user_settings.current_monday()
    settings = {
        "week_one_start": current.isoformat(),
        "purpose_mode": "default",
        "detail_level": "standard",
        "tone": "natural",
    }
    events = list(
        agent.stream_chat(
            "owner",
            "session",
            "本周完成接口",
            "fake-key",
            "https://example.invalid",
            "fake-model",
            settings=settings,
            attachment_context="附件绝密正文：SECRET-ATTACHMENT-CONTENT",
        )
    )
    week_id = next(event["week_id"] for event in events if event["type"] == "final")
    row = storage.get_week("owner", week_id)
    assert row["raw_input"] == "本周完成接口"
    assert "SECRET-ATTACHMENT-CONTENT" not in row["raw_input"]


def test_closed_stream_rolls_back_unfinished_user_turn(monkeypatch):
    agent.clear_conversations()

    class Chunk:
        choices = [
            type(
                "Choice",
                (),
                {"delta": type("Delta", (), {"content": "这是一段足够长的流式追问文本。"})()},
            )()
        ]

    class Completions:
        def create(self, **kwargs):
            return [Chunk()]

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": Completions()})()

    monkeypatch.setattr(agent, "OpenAI", FakeOpenAI)
    stream = agent.stream_chat("owner", "interrupted", "不应残留", "key", "https://example.invalid", "model")
    next(stream)
    stream.close()
    snapshot = runtime_store.load_conversation(
        "owner",
        "interrupted",
        now=agent.time.time(),
        ttl_seconds=agent.CONVERSATION_TTL_SECONDS,
    )
    assert snapshot
    history = snapshot.data["messages"]
    assert [message["role"] for message in history] == ["system"]


def test_idle_conversation_cleanup_honors_ttl(monkeypatch):
    agent.clear_conversations()
    runtime_store.save_conversation(
        "owner",
        "expired",
        [{"role": "system", "content": "system"}],
        expected_revision=None,
        expected_epoch=runtime_store.namespace_epoch("owner", "conversation"),
        now=10.0,
        ttl_seconds=agent.CONVERSATION_TTL_SECONDS,
        max_records=agent.MAX_CONVERSATIONS,
    )
    monkeypatch.setattr(agent.time, "time", lambda: 10.0 + agent.CONVERSATION_TTL_SECONDS + 1)

    agent.cleanup_expired_conversations()

    assert (
        runtime_store.load_conversation(
            "owner",
            "expired",
            now=agent.time.time(),
            ttl_seconds=agent.CONVERSATION_TTL_SECONDS,
        )
        is None
    )
