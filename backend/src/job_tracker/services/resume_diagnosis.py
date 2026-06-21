"""M2 履歷診斷：針對目標職位 + 薪資，分析履歷優勢／待補強。純 LLM 分析。"""

from job_tracker import llm
from job_tracker.schemas import ResumeDiagnosis, ResumeTarget


async def diagnose(target: ResumeTarget) -> ResumeDiagnosis:
    """回傳履歷對該職位的優勢與缺口。

    TODO：設計穩定的 prompt 與輸出解析（建議讓 LLM 回 JSON）。
    目前為串接骨架。
    """
    prompt = (
        f"目標職位：{target.target_title}\n"
        f"期望月薪：{target.expected_salary or '未指定'}\n\n"
        f"履歷內容：\n{target.resume_text}\n\n"
        "請分析這份履歷對該職位的『優勢』與『待補強』。"
    )
    _ = await llm.complete(prompt)
    raise NotImplementedError("解析 LLM 輸出為 ResumeDiagnosis 待實作（第二週）")
