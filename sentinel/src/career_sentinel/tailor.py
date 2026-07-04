from __future__ import annotations

from . import llm
from .models import JobDetail, TailoredApplication

_SYSTEM = "你是一位專業的求職顧問，協助求職者針對特定職缺客製化履歷重點與求職信。"


def build_prompt(resume_text: str, target_title: str, jd: JobDetail) -> str:
    return (
        f"求職者目標職位：{target_title}\n"
        f"履歷全文：\n{resume_text}\n\n"
        f"目標職缺：{jd.title}（{jd.company}）\n"
        f"職缺需求：\n{jd.description}\n"
        f"工作經驗：{jd.work_exp}　學歷：{jd.education}\n"
        f"技能：{', '.join(jd.specialties)}\n\n"
        "請針對此職缺客製化，只回 JSON，格式：\n"
        '{"resume_tips": ["履歷中應強調的重點…"], '
        '"resume_adjustments": ["建議的調整…"], '
        '"missing_keywords": ["履歷缺少但職缺看重的關鍵字…"], '
        '"cover_letter": "求職信全文"}\n'
        "規則：resume_tips/adjustments 只給建議，**不要重寫整份履歷、不得捏造求職者沒有的經歷**；"
        "cover_letter 為 300–400 字繁體中文求職信，對應此職缺、語氣專業誠懇、"
        "只根據履歷已有的事實。"
    )


def tailor_application(
    resume_text: str, target_title: str, jd: JobDetail, *, client=None
) -> TailoredApplication:
    result = llm.parse_json(
        build_prompt(resume_text, target_title, jd),
        TailoredApplication,
        system=_SYSTEM,
        client=client,
        feature="客製化",
    )
    result.job_title = jd.title
    result.company = jd.company
    return result
