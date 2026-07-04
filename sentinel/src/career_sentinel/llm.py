from __future__ import annotations

import json
import re
from datetime import datetime

import httpx

from . import usage
from .config import foundry_settings, llm_provider, llm_settings


def _extract_json(text: str) -> str:
    """去 markdown 圍欄、取第一個 { 到最後一個 }。"""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _with_today(system: str | None) -> str:
    """所有 LLM 呼叫的 system 都附上今天日期，避免模型停留在訓練截止時間。"""
    today = f"今天日期：{datetime.now().strftime('%Y-%m-%d')}"
    return f"{system}\n\n{today}" if system else today


def parse_json(prompt: str, model_cls, *, system: str | None = None, client=None, feature: str = ""):
    """要 JSON、驗進 Pydantic model_cls。依 provider 走 OpenAI 相容或 Foundry(Anthropic)。"""
    system = _with_today(system)
    provider = llm_provider()
    if provider == "openai":
        return _openai_parse_json(prompt, model_cls, system, client, feature)
    if provider == "foundry":
        return _foundry_parse_json(prompt, model_cls, system, client, feature)
    raise RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")


def _openai_parse_json(prompt, model_cls, system, client, feature):
    cfg = llm_settings()
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    http = client or httpx.Client(timeout=120)
    owns_client = client is None
    try:
        resp = http.post(
            f"{cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={
                "model": cfg.model,
                "messages": messages,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        usage.record(feature, cfg.model, data.get("usage"))
        content = data["choices"][0]["message"]["content"]
        return model_cls.model_validate(json.loads(_extract_json(content)))
    finally:
        if owns_client:
            http.close()


def _foundry_parse_json(prompt, model_cls, system, client, feature):
    fs = foundry_settings()
    if client is None:
        from anthropic import AnthropicFoundry

        client = AnthropicFoundry(api_key=fs.api_key, base_url=fs.base_url)
    sys_text = (system + "\n\n" if system else "") + "只輸出單一 JSON 物件，不要任何額外文字或 markdown。"
    resp = client.messages.create(
        model=fs.model,
        max_tokens=4096,
        system=sys_text,
        messages=[{"role": "user", "content": prompt}],
    )
    usage.record(feature, fs.model, getattr(resp, "usage", None))
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    return model_cls.model_validate(json.loads(_extract_json(text)))


def chat_stream(messages: list[dict], *, system: str | None = None, client=None, feature: str = ""):
    """多輪對話串流，yield 文字增量。依 provider 走 OpenAI 相容或 Foundry(Anthropic)。"""
    system = _with_today(system)
    provider = llm_provider()
    if provider == "openai":
        yield from _openai_chat_stream(messages, system, client, feature)
    elif provider == "foundry":
        yield from _foundry_chat_stream(messages, system, client, feature)
    else:
        raise RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")


def _openai_chat_stream(messages, system, client, feature):
    cfg = llm_settings()
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)
    http = client or httpx.Client(timeout=300)
    owns_client = client is None
    last_usage = None
    try:
        with http.stream(
            "POST",
            f"{cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={"model": cfg.model, "messages": msgs, "stream": True,
                  "stream_options": {"include_usage": True}},
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload == "[DONE]":
                    break
                data = json.loads(payload)
                if data.get("usage"):
                    last_usage = data["usage"]
                choices = data.get("choices") or []
                if not choices:
                    continue
                text = choices[0].get("delta", {}).get("content")
                if text:
                    yield text
        usage.record(feature, cfg.model, last_usage)
    finally:
        if owns_client:
            http.close()


def _foundry_chat_stream(messages, system, client, feature):
    fs = foundry_settings()
    if client is None:
        from anthropic import AnthropicFoundry

        client = AnthropicFoundry(api_key=fs.api_key, base_url=fs.base_url)
    kwargs: dict = {"model": fs.model, "max_tokens": 4096, "messages": messages}
    if system:
        kwargs["system"] = system
    with client.messages.stream(**kwargs) as stream:
        yield from stream.text_stream
        final = stream.get_final_message()
    usage.record(feature, fs.model, getattr(final, "usage", None))
