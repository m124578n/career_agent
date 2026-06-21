from job_tracker.schemas import Job, JobDetail, ResumeTarget
from job_tracker.services import cover_letter


def make_job() -> Job:
    return Job(
        job_id="1",
        code="abc",
        title="Backend Engineer",
        company="某科技公司",
        url="https://www.104.com.tw/job/abc",
    )


async def test_generate_uses_resume_and_full_jd(monkeypatch):
    captured: dict = {}

    async def fake_complete(prompt, *, system="", max_tokens=2048, client=None):
        captured["prompt"] = prompt
        captured["max_tokens"] = max_tokens
        return "敬啟者，我對貴公司的職缺深感興趣……"

    monkeypatch.setattr(cover_letter.llm, "complete", fake_complete)

    target = ResumeTarget(target_title="後端工程師", resume_text="5 年 Python 經驗")
    detail = JobDetail(description="需要 FastAPI 與 Kafka 經驗")

    text = await cover_letter.generate(target, make_job(), detail)

    assert text.startswith("敬啟者")
    # 用了履歷與完整 JD
    assert "5 年 Python 經驗" in captured["prompt"]
    assert "Kafka" in captured["prompt"]


async def test_generate_falls_back_to_snippet_without_detail(monkeypatch):
    captured: dict = {}

    async def fake_complete(prompt, **kwargs):
        captured["prompt"] = prompt
        return "letter"

    monkeypatch.setattr(cover_letter.llm, "complete", fake_complete)

    job = make_job()
    job.description = "職缺摘要：Python 後端"
    target = ResumeTarget(target_title="後端", resume_text="履歷")

    await cover_letter.generate(target, job)
    assert "職缺摘要：Python 後端" in captured["prompt"]
