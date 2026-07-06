"""SP9 公司評價 web 研究：LLM 自帶 web search 查評價、解析成 CompanyResearch。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import httpx

from . import llm, usage
from .config import foundry_settings, llm_provider, llm_settings
from .models import CompanyResearch

RESEARCH_TTL_DAYS = 7  # 快取有效天數
_TIMEOUT = 180  # web search 呼叫可能 20-60 秒，放寬


def build_research_prompt(name: str) -> str:
    return (
        f"請用網路搜尋研究台灣公司「{name}」的求職者評價。"
        f"建議搜尋關鍵字：「{name} 評價」「{name} 面試」「{name} 薪水 ptt dcard」。"
        "優先參考台灣站點（面試趣、比薪水、Dcard、PTT、Google 評論）。\n\n"
        "整理後只輸出單一 JSON 物件（不要 markdown 圍欄、不要任何其他文字），格式：\n"
        '{"summary": "總評一段（150字內）", "pros": ["優點…"], "cons": ["缺點…"], '
        '"salary_notes": "薪資觀察", "interview_notes": "面試觀察", '
        '"risk_level": "low|mid|high", '
        '"sources": [{"title": "來源標題", "url": "https://…"}]}\n'
        "規則：risk_level 依負評比例與嚴重度判斷（low=評價普遍正面、mid=毀譽參半或資料少、"
        "high=負評集中且嚴重）；查不到資料的欄位留空字串或空陣列，並在 summary 註明資料稀少；"
        "sources 只列你實際參考到的網頁。"
    )


def web_search_complete(prompt: str, *, feature: str, client=None) -> str:
    """依 provider 跑一次帶 web search 的 LLM 補全，回文字。"""
    provider = llm_provider()
    if provider == "openai":
        return _openai_research(prompt, client, feature)
    if provider == "foundry":
        return _foundry_research(prompt, client, feature)
    raise RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")


def research_company(name: str, *, client=None, feature: str = "公司研究") -> CompanyResearch:
    prompt = build_research_prompt(name)
    text = web_search_complete(prompt, feature=feature, client=client)
    r = CompanyResearch.model_validate(json.loads(llm._extract_json(text)))
    r.company = name
    r.researched_at = datetime.now().isoformat(timespec="seconds")
    return r


def _openai_research(prompt, client, feature):
    cfg = llm_settings()
    http = client or httpx.Client(timeout=_TIMEOUT)
    owns_client = client is None
    try:
        resp = http.post(
            f"{cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={
                "model": cfg.model + ":online",  # OpenRouter web search 慣例；非 OpenRouter 的 OpenAI 相容端點不支援此後綴
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        usage.record(feature, cfg.model, data.get("usage"))
        return data["choices"][0]["message"]["content"]
    finally:
        if owns_client:
            http.close()


def _foundry_research(prompt, client, feature):
    fs = foundry_settings()
    if client is None:
        from anthropic import AnthropicFoundry

        client = AnthropicFoundry(api_key=fs.api_key, base_url=fs.base_url, timeout=_TIMEOUT)
    resp = client.messages.create(
        model=fs.model,
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        messages=[{"role": "user", "content": prompt}],
    )
    usage.record(feature, fs.model, getattr(resp, "usage", None))
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def is_fresh(r: CompanyResearch, *, now: datetime | None = None) -> bool:
    """researched_at 在 TTL 內？空/壞格式視為過期。"""
    try:
        t = datetime.fromisoformat(r.researched_at)
    except ValueError:
        return False
    return ((now or datetime.now()) - t) <= timedelta(days=RESEARCH_TTL_DAYS)
