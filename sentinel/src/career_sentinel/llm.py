from __future__ import annotations

import json
import re

import httpx

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


def parse_json(prompt: str, model_cls, *, system: str | None = None, client=None):
    """要 JSON、驗進 Pydantic model_cls。依 provider 走 OpenAI 相容或 Foundry(Anthropic)。"""
    provider = llm_provider()
    if provider == "openai":
        return _openai_parse_json(prompt, model_cls, system, client)
    if provider == "foundry":
        return _foundry_parse_json(prompt, model_cls, system, client)
    raise RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")


def _openai_parse_json(prompt, model_cls, system, client):
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
        content = resp.json()["choices"][0]["message"]["content"]
        return model_cls.model_validate(json.loads(_extract_json(content)))
    finally:
        if owns_client:
            http.close()


def _foundry_parse_json(prompt, model_cls, system, client):
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
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    return model_cls.model_validate(json.loads(_extract_json(text)))
