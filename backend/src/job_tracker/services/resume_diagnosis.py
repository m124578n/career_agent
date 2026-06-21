"""M2 履歷診斷：針對目標職位 + 薪資，分析履歷優勢／待補強。純 LLM 分析。"""

from job_tracker import llm
from job_tracker.schemas import ResumeDiagnosis, ResumeTarget

_SYSTEM = "你是一位專業的求職顧問，請針對指定職位客觀分析履歷的優勢與待補強之處。"


def _build_prompt(target: ResumeTarget) -> str:
    return (
        f"目標職位：{target.target_title}\n"
        f"期望月薪：{target.expected_salary or '未指定'}\n\n"
        f"履歷內容：\n{target.resume_text}\n\n"
        "請針對『這個職位 + 這個薪資』分析這份履歷的『優勢』與『待補強』。"
    )


async def diagnose(target: ResumeTarget, *, client=None) -> ResumeDiagnosis:
    """回傳履歷對該職位的優勢與缺口（M2）。"""
    return await llm.parse(
        _build_prompt(target), ResumeDiagnosis, system=_SYSTEM, client=client
    )
