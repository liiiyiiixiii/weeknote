import pytest
from pydantic import ValidationError

from app import organize
from app.schemas import Organized


def test_parse_plain_json():
    assert organize.parse_llm_output('{"a": 1}') == {"a": 1}


def test_parse_strips_code_fence():
    fence = chr(96) * 3
    raw = fence + "json\n" + '{"a": 1}\n' + fence
    assert organize.parse_llm_output(raw) == {"a": 1}


def test_parse_strips_surrounding_text():
    raw = '好的，结果如下：\n{"a": 1}\n希望对你有帮助'
    assert organize.parse_llm_output(raw) == {"a": 1}


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        organize.parse_llm_output("这不是 JSON")


def test_build_messages_injects_date_context():
    msgs = organize.build_messages("笔记内容", "今天是 2025-08-15（星期五）。")
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"].startswith("今天是 2025-08-15")
    assert "笔记内容" in msgs[1]["content"]


def test_build_messages_without_date_context():
    msgs = organize.build_messages("笔记内容", "")
    assert msgs[1]["content"] == "笔记内容"


def test_output_contract_rejects_invalid_category_date_and_extra_fields():
    base = {
        "report": {
            "title": "周报",
            "sections": [
                {
                    "category": "随便",
                    "items": [{"date": "2026-02-30", "summary": "事项"}],
                }
            ],
        },
        "tech_summary": {"title": "技术", "topics": []},
        "unexpected": True,
    }
    with pytest.raises(ValidationError):
        Organized.model_validate(base)


def test_organize_retries_when_json_fails_business_contract(monkeypatch):
    invalid = '{"report":{"sections":[{"category":"非法","items":[{"summary":"A"}]}]},"tech_summary":{"topics":[]}}'
    valid = '{"report":{"sections":[{"category":"工作","items":[{"summary":"A"}]}]},"tech_summary":{"topics":[]}}'
    responses = [invalid, valid]

    class Completions:
        def __init__(self):
            self.calls = 0
            self.kwargs = []

        def create(self, **kwargs):
            self.kwargs.append(kwargs)
            content = responses[self.calls]
            self.calls += 1
            message = type("Message", (), {"content": content})()
            return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

    completions = Completions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": completions})()

    monkeypatch.setattr(organize, "OpenAI", FakeOpenAI)
    result = organize.organize("本周完成 A", "key", "https://example.invalid", "model")
    assert result["report"]["sections"][0]["category"] == "工作"
    assert completions.calls == 2
    assert all(call["extra_body"] == {"thinking": {"type": "disabled"}} for call in completions.kwargs)
