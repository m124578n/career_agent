from __future__ import annotations

from . import llm
from .models import ResumeDiagnosis

_SYSTEM = "你是一位專業的求職顧問，請針對指定職位客觀分析履歷的優勢與待補強之處。"


def build_prompt(resume_text: str, target_title: str, expected_salary: int | None) -> str:
    return (
        f"目標職位：{target_title}\n"
        f"期望月薪：{expected_salary or '未指定'}\n\n"
        f"履歷內容：\n{resume_text}\n\n"
        "請針對『這個職位 + 這個薪資』分析這份履歷的『優勢』與『待補強』。"
        '只回 JSON，格式 {"strengths": ["..."], "gaps": ["..."]}。'
    )


def diagnose(resume_text: str, target_title: str, expected_salary: int | None, *, client=None) -> ResumeDiagnosis:
    return llm.parse_json(
        build_prompt(resume_text, target_title, expected_salary),
        ResumeDiagnosis,
        system=_SYSTEM,
        client=client,
        feature="履歷健檢",
    )
