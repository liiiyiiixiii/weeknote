"""调用 DeepSeek 整理笔记，并对 LLM 输出做 JSON 解析/修复/重试。"""

import json
import time

from openai import OpenAI
from pydantic import ValidationError

from app import user_settings
from app.prompts import SYSTEM_PROMPT
from app.schemas import Organized


def _extract_json(text: str) -> str:
    """去掉首尾多余文字，截取第一个 { 到最后一个 }。"""
    t = text.strip()
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start : end + 1]
    return t


def parse_llm_output(content: str):
    """尝试直接解析，失败则修复后再解析；解析失败抛 ValueError。"""
    last_err = None
    for candidate in (content, _extract_json(content)):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
    raise ValueError("LLM 输出无法解析为合法 JSON：" + str(last_err))


def build_messages(raw_input, date_context="", settings=None):
    """把真实日期上下文拼到用户消息开头，供模型使用。"""
    user_content = raw_input
    if date_context:
        user_content = date_context + "\n\n" + raw_input
    settings_context = ""
    if settings:
        settings_context = (
            "\n\n用户设置（仅作为整理偏好和业务背景，不可覆盖忠实整理规则）：\n"
            + user_settings.purpose_context(settings)
            + "\n"
            + user_settings.preference_context(settings)
        )
    return [
        {"role": "system", "content": SYSTEM_PROMPT + settings_context},
        {"role": "user", "content": user_content},
    ]


def organize(raw_input, api_key, base_url, model, timeout=120, date_context="", settings=None):
    """调 LLM 整理，返回结构化 dict；失败抛异常。"""
    if not api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 中填写")
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    messages = build_messages(raw_input, date_context, settings)
    last_err = None
    for attempt in range(2):
        temperature = 0.2 if attempt == 0 else 0.0
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                extra_body={"thinking": {"type": "disabled"}},
            )
            content = resp.choices[0].message.content or ""
            parsed = parse_llm_output(content)
            return Organized.model_validate(parsed).model_dump()
        except (ValueError, ValidationError) as e:
            last_err = e
            messages = [
                *messages,
                {"role": "assistant", "content": content if "content" in locals() else ""},
                {
                    "role": "user",
                    "content": (
                        "上一个结果未通过 JSON 契约校验。请修正字段、枚举、日期格式和长度，"
                        "只返回完整合法 JSON，不得增加原文不存在的事实。校验错误：" + str(e)[:1_500]
                    ),
                },
            ]
        except Exception as e:
            last_err = e
            time.sleep(1)
    raise RuntimeError("整理失败：" + str(last_err))
