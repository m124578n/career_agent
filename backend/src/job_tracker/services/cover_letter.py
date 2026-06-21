"""M5 求職信生成：對想投的職缺，產生一封堪用的 cover letter。"""

from job_tracker import llm
from job_tracker.schemas import Job, ResumeTarget


async def generate(target: ResumeTarget, job: Job) -> str:
    """依履歷與職缺生成求職信純文字。"""
    prompt = (
        f"履歷：\n{target.resume_text}\n\n"
        f"職缺：{job.title} @ {job.company}\n{job.description}\n\n"
        "請以求職者第一人稱寫一封繁體中文求職信，語氣專業、具體連結履歷與職缺需求。"
    )
    return await llm.complete(prompt, max_tokens=1500)
