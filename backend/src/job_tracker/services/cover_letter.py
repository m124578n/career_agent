"""M5 求職信生成：對想投的職缺，產生一封堪用的 cover letter。"""

from job_tracker import llm
from job_tracker.schemas import Job, JobDetail, ResumeTarget

_SYSTEM = "你是一位專業的求職顧問，擅長撰寫具體、真誠、不浮誇的求職信。"


async def generate(
    target: ResumeTarget,
    job: Job,
    detail: JobDetail | None = None,
    *,
    client=None,
) -> str:
    """依履歷與職缺生成繁體中文求職信純文字。有完整 JD 時優先使用。"""
    jd = detail.description if detail and detail.description else job.description
    prompt = (
        f"求職者履歷：\n{target.resume_text}\n\n"
        f"應徵職缺：{job.title} @ {job.company}\n"
        f"職缺內容：\n{jd}\n\n"
        "請以求職者第一人稱寫一封繁體中文求職信：語氣專業、真誠不浮誇，"
        "具體連結履歷經驗與職缺需求，約 300~400 字，不要客套套語堆砌。"
    )
    return await llm.complete(prompt, system=_SYSTEM, max_tokens=1500, client=client)
