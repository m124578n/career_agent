"""SP22 offer 談判建議：LLM+web search 依 offer 明細與競品給議價策略與話術。"""
from __future__ import annotations

import json
from datetime import datetime

from . import llm, research
from .models import NegotiationAdvice, OfferDetail


def build_negotiate_prompt(offer: OfferDetail, company: str, title: str,
                           other_offers: list[dict], expected_salary: int | None) -> str:
    lines = [f"我拿到「{company}」的「{title}」offer，請幫我想議價策略與話術。", "", "這個 offer 條件："]
    if offer.salary_year is not None:
        lines.append(f"- 年薪：{offer.salary_year}")
    if offer.salary_month is not None:
        lines.append(f"- 月薪：{offer.salary_month}")
    if offer.location:
        lines.append(f"- 地點：{offer.location}")
    if offer.level:
        lines.append(f"- 職級：{offer.level}")
    if offer.start_date:
        lines.append(f"- 到職日：{offer.start_date}")
    if offer.notes:
        lines.append(f"- 備註：{offer.notes}")
    if expected_salary:
        lines.append(f"\n我的期望月薪：{expected_salary}")
    if other_offers:
        lines.append("\n我手上其他 offer（可當競品槓桿）：")
        for o in other_offers:
            parts = [o.get("company") or "（某公司）"]
            if o.get("salary_year") is not None:
                parts.append(f"年薪 {o['salary_year']}")
            elif o.get("salary_month") is not None:
                parts.append(f"月薪 {o['salary_month']}")
            lines.append("- " + "，".join(parts))
    lines += [
        "",
        "請用網路搜尋這個職位在台灣的市場薪資區間（可參考比薪水、104 薪資、Glassdoor、Dcard 等）。",
        "把我手上其他 offer 當作議價槓桿。只輸出單一 JSON 物件（不要 markdown 圍欄、不要其他文字），格式：",
        '{"summary": "一句話：能不能談、談多少", "market_assessment": "相對台灣市場行情的評估", '
        '"leverage_points": ["你的籌碼…"], "suggested_ask": "建議開多少或談什麼（薪資/簽約金/股票/到職日）", '
        '"scripts": ["可直接用的議價話術…"], "risks": ["風險/注意事項…"], '
        '"sources": [{"title": "來源標題", "url": "https://…"}]}',
        "規則：查不到市場行情時在 market_assessment 註明資料稀少，並仍基於競品 offer 與期望薪資給策略；"
        "sources 只列實際參考到的網頁。",
    ]
    return "\n".join(lines)


def negotiate_offer(offer: OfferDetail, company: str, title: str,
                    other_offers: list[dict], expected_salary: int | None,
                    *, client=None, feature: str = "談判建議") -> NegotiationAdvice:
    prompt = build_negotiate_prompt(offer, company, title, other_offers, expected_salary)
    text = research.web_search_complete(prompt, feature=feature, client=client)
    r = NegotiationAdvice.model_validate(json.loads(llm._extract_json(text)))
    r.advised_at = datetime.now().isoformat(timespec="seconds")
    return r
