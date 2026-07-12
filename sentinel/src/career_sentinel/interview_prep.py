"""面試準備助手：依 JD + 履歷 + 缺口生考題/防雷/亮點/清單；深度模式加網搜公司面試心得。"""
from __future__ import annotations

import json
from datetime import datetime

from . import llm, research
from .models import InterviewPrep, JobDetail

_RESUME_MAX = 6000


def build_interview_prep_prompt(jd: JobDetail, resume_text: str, gaps: list[str],
                                target_title: str, *, deep: bool) -> str:
    lines = [
        f"我下週要面試「{jd.company or '（公司未知）'}」的「{jd.title or target_title or '（職稱未知）'}」，"
        "請幫我做面試準備。",
        "",
        "職缺 JD：",
        f"- 職稱：{jd.title}",
        f"- 公司：{jd.company}",
        f"- 需求經驗：{jd.work_exp}；學歷：{jd.education}",
        f"- 專長技能：{'、'.join(jd.specialties) or '（未列）'}",
        f"- JD 內文：{(jd.description or '')[:2000]}",
        "",
        f"我的履歷（前 {_RESUME_MAX} 字）：\n{resume_text[:_RESUME_MAX] or '（未提供）'}",
    ]
    if gaps:
        lines += ["", "我對這個職缺的已知缺口（比對結果）：", *[f"- {g}" for g in gaps]]
    else:
        lines += ["", "（沒有現成的缺口分析，請你從 JD 與我的履歷自行推斷我可能被追問的弱點。）"]
    if deep:
        lines += [
            "",
            f"請用網路搜尋「{jd.company}」這間公司在台灣的面試心得與考古題"
            "（可參考 Dcard、PTT Tech_Job、Glassdoor、面試趣），把常見題型與面試流程納入考量；"
            "sources 只列實際參考到的網頁。",
        ]
    lines += [
        "",
        "只輸出單一 JSON 物件（不要 markdown 圍欄、不要其他文字），格式：",
        '{"likely_questions": ["可能被問的題目…"], '
        '"gap_watchouts": ["針對我缺口可能被追問的點 + 建議怎麼回…"], '
        '"talking_points": ["我該主動帶出的亮點…"], '
        '"prep_checklist": ["面試前要複習/準備的項目…"]'
        + (', "sources": [{"title": "來源標題", "url": "https://…"}]' if deep else "")
        + "}",
    ]
    return "\n".join(lines)


def prepare_interview(jd: JobDetail, resume_text: str, gaps: list[str], target_title: str,
                      *, deep: bool = False, client=None, feature: str = "面試準備") -> InterviewPrep:
    prompt = build_interview_prep_prompt(jd, resume_text, gaps, target_title, deep=deep)
    if deep:
        text = research.web_search_complete(prompt, feature=feature, client=client)
        r = InterviewPrep.model_validate(json.loads(llm._extract_json(text)))
    else:
        r = llm.parse_json(prompt, InterviewPrep, feature=feature, client=client)
    r.deep = deep
    r.prepared_at = datetime.now().isoformat(timespec="seconds")
    return r
