from __future__ import annotations

from . import llm
from .models import JobDetail, MatchResult

_SYSTEM = "你是一位專業的求職顧問，請客觀評估履歷與職缺的契合度。"


def build_prompt(resume_text: str, target_title: str, jd: JobDetail) -> str:
    return (
        f"求職者目標職位：{target_title}\n"
        f"履歷：\n{resume_text}\n\n"
        f"職缺：{jd.title}（{jd.company}）\n"
        f"職缺需求：\n{jd.description}\n"
        f"工作經驗：{jd.work_exp}　學歷：{jd.education}\n"
        f"技能：{', '.join(jd.specialties)}\n\n"
        "請評估履歷與此職缺的契合度（0~100 分），並列出契合理由與缺少的技能/待補強。\n"
        '只回 JSON，格式 {"score": <0-100 整數>, "reasons": ["..."], "gaps": ["..."]}。'
    )


def match(resume_text: str, target_title: str, jd: JobDetail, *, client=None) -> MatchResult:
    return llm.parse_json(
        build_prompt(resume_text, target_title, jd),
        MatchResult,
        system=_SYSTEM,
        client=client,
        feature="JD比對",
    )
