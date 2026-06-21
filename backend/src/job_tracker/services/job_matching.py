"""M4 契合度分析：逐筆把職缺與履歷比對，給出 0~100 分與理由/缺口。"""

from job_tracker import llm
from job_tracker.schemas import Job, JobMatch, ResumeTarget


async def match(target: ResumeTarget, job: Job) -> JobMatch:
    """分析單筆職缺與履歷的契合度。

    TODO（第二週）：prompt 設計 + JSON 輸出解析 + 契合度維度（技能/年資/薪資/地點/產業）。
    """
    prompt = (
        f"履歷：\n{target.resume_text}\n\n"
        f"職缺：{job.title} @ {job.company}\n{job.description}\n\n"
        "請評估契合度（0~100）、列出契合理由與缺口。"
    )
    _ = await llm.complete(prompt)
    raise NotImplementedError("契合度分析待實作（第二週）")


async def match_batch(target: ResumeTarget, jobs: list[Job]) -> list[JobMatch]:
    """逐筆分析並依契合度排序。"""
    results = [await match(target, job) for job in jobs]
    return sorted(results, key=lambda m: m.score, reverse=True)
