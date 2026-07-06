import pytest

from career_sentinel import negotiate, research
from career_sentinel.models import NegotiationAdvice, OfferDetail


def test_web_search_complete_dispatch(monkeypatch):
    monkeypatch.setattr(research, "_foundry_research", lambda p, c, f: "FOUNDRY")
    monkeypatch.setattr(research, "_openai_research", lambda p, c, f: "OPENAI")
    monkeypatch.setattr(research, "llm_provider", lambda: "foundry")
    assert research.web_search_complete("hi", feature="x") == "FOUNDRY"
    monkeypatch.setattr(research, "llm_provider", lambda: "openai")
    assert research.web_search_complete("hi", feature="x") == "OPENAI"
    monkeypatch.setattr(research, "llm_provider", lambda: "")
    with pytest.raises(RuntimeError):
        research.web_search_complete("hi", feature="x")


def test_build_negotiate_prompt_has_offer_and_competitors():
    p = negotiate.build_negotiate_prompt(
        OfferDetail(salary_year=1200000, location="台北"), "甲公司", "後端工程師",
        [{"company": "乙公司", "salary_year": 1400000}], 90000)
    assert "甲公司" in p and "後端工程師" in p and "1200000" in p
    assert "乙公司" in p and "1400000" in p   # 競品槓桿
    assert "90000" in p                        # 期望薪資
    assert "JSON" in p


def test_negotiate_offer_parses(monkeypatch):
    fake = ('{"summary":"可談","market_assessment":"低於行情","leverage_points":["有競品offer"],'
            '"suggested_ask":"開到140萬","scripts":["我另有一個 offer…"],"risks":["別太硬"],'
            '"sources":[{"title":"比薪水","url":"https://x"}]}')
    monkeypatch.setattr(research, "web_search_complete", lambda prompt, **k: fake)
    r = negotiate.negotiate_offer(OfferDetail(salary_year=1200000), "甲", "後端", [], 90000)
    assert isinstance(r, NegotiationAdvice)
    assert r.summary == "可談" and r.suggested_ask == "開到140萬"
    assert r.leverage_points == ["有競品offer"] and r.advised_at
    assert r.sources[0].url == "https://x"
