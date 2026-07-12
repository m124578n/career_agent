import json

from career_sentinel import interview_prep, llm, research
from career_sentinel.models import InterviewPrep, JobDetail


_JD = JobDetail(title="後端工程師", company="甲公司", description="需 Python、FastAPI、SQL 三年經驗",
                work_exp="3 年以上", education="大學", specialties=["Python", "FastAPI"])


def test_prompt_contains_jd_resume_gaps_and_deep(monkeypatch):
    p = interview_prep.build_interview_prep_prompt(
        _JD, "我做過 Django 專案", ["缺 FastAPI 經驗"], "後端工程師", deep=False)
    assert "後端工程師" in p and "甲公司" in p and "Django" in p and "缺 FastAPI 經驗" in p
    assert "面試心得" not in p  # 快版不談搜尋
    p2 = interview_prep.build_interview_prep_prompt(_JD, "履歷", [], "後端工程師", deep=True)
    assert "面試心得" in p2 and "甲公司" in p2  # 深度版指示搜公司面試心得


def test_prepare_interview_fast(monkeypatch):
    def fake_parse(prompt, model_cls, *, system=None, client=None, feature=""):
        return model_cls.model_validate({
            "likely_questions": ["為什麼想來甲公司"],
            "gap_watchouts": ["會被追問 FastAPI"],
            "talking_points": ["Django 經驗可遷移"],
            "prep_checklist": ["複習 FastAPI 基礎"],
        })
    monkeypatch.setattr(llm, "parse_json", fake_parse)
    r = interview_prep.prepare_interview(_JD, "履歷", ["缺 FastAPI"], "後端工程師", deep=False)
    assert isinstance(r, InterviewPrep)
    assert r.deep is False and r.prepared_at
    assert r.likely_questions == ["為什麼想來甲公司"] and r.sources == []


def test_prepare_interview_deep_uses_web_search(monkeypatch):
    payload = {
        "likely_questions": ["系統設計"], "gap_watchouts": [], "talking_points": [],
        "prep_checklist": [], "sources": [{"title": "Dcard 面試心得", "url": "https://dcard.tw/x"}],
    }
    monkeypatch.setattr(research, "web_search_complete",
                        lambda prompt, *, feature, client=None: json.dumps(payload, ensure_ascii=False))
    r = interview_prep.prepare_interview(_JD, "履歷", [], "後端工程師", deep=True)
    assert r.deep is True and len(r.sources) == 1 and r.sources[0].url == "https://dcard.tw/x"
