"""M4 契合度分析：把職缺與履歷比對，給出 0~100 分與理由/缺口。"""

from job_tracker import llm
from job_tracker.schemas import Job, JobDetail, JobMatch, MatchAnalysis, ResumeTarget
from job_tracker.services.external_apply import requires_external_apply

_SYSTEM = "你是一位專業的求職顧問，請客觀評估履歷與職缺的契合度。"


def _build_prompt(target: ResumeTarget, job: JobDetail) -> str:
    return (
        f"求職者目標職位：{target.target_title}\n"
        f"期望月薪：{target.expected_salary or '未指定'}\n\n"
        f"履歷：\n{target.resume_text}\n\n"
        f"職缺需求：\n{job.description}\n"
        f"工作經驗：{job.work_exp}　學歷：{job.education}\n"
        f"技能：{', '.join(job.specialties)}\n\n"
        "請評估契合度（0~100 分），並列出契合理由與待補強缺口。\n"
        "另外列出職缺 JD 中明確提到的福利（如特休、年終、遠端、彈性上班、股票等），"
        "每項標籤化、不超過 8 字、最多 6 項；JD 沒提到就不要列、不要臆測。"
    )


async def analyze(
    target: ResumeTarget,
    job: Job,
    detail: JobDetail,
    *,
    client=None,
) -> JobMatch:
    """分析單筆職缺與履歷的契合度，回傳 JobMatch。"""
    analysis: MatchAnalysis = await llm.parse(
        _build_prompt(target, detail), MatchAnalysis, system=_SYSTEM, client=client
    )
    return JobMatch(
        job=job,
        score=analysis.score,
        reasons=analysis.reasons,
        gaps=analysis.gaps,
        benefits=analysis.benefits,
        requires_external_apply=requires_external_apply(detail.description),
    )


async def analyze_batch(
    target: ResumeTarget,
    jobs: list[tuple[Job, JobDetail]],
    *,
    client=None,
) -> list[JobMatch]:
    """逐筆分析並依契合度由高到低排序。"""
    results = [await analyze(target, job, detail, client=client) for job, detail in jobs]
    return sorted(results, key=lambda m: m.score, reverse=True)
