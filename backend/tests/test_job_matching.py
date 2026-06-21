from job_tracker import llm
from job_tracker.schemas import Job, JobDetail, MatchAnalysis, ResumeTarget
from job_tracker.services import job_matching


def make_target() -> ResumeTarget:
    return ResumeTarget(
        target_title="Python 後端工程師",
        expected_salary=60000,
        resume_text="5 年 Python / FastAPI 經驗",
    )


def make_job(job_id: str = "1") -> Job:
    return Job(
        job_id=job_id,
        code="abc",
        title="Python Engineer",
        company="某公司",
        url="https://www.104.com.tw/job/abc",
    )


def make_detail(description: str = "一般職缺描述") -> JobDetail:
    return JobDetail(description=description, specialties=["Python"])


async def test_analyze_builds_jobmatch_from_llm(monkeypatch):
    async def fake_parse(prompt, schema, **kwargs):
        assert schema is MatchAnalysis
        # prompt 應帶入履歷與職缺資訊
        assert "FastAPI" in prompt
        return MatchAnalysis(score=82, reasons=["技能高度符合"], gaps=["缺 K8s 經驗"])

    monkeypatch.setattr(llm, "parse", fake_parse)

    m = await job_matching.analyze(make_target(), make_job(), make_detail())
    assert m.score == 82
    assert m.job.job_id == "1"
    assert m.reasons == ["技能高度符合"]
    assert m.gaps == ["缺 K8s 經驗"]
    assert m.requires_external_apply is False


async def test_analyze_flags_external_apply(monkeypatch):
    async def fake_parse(prompt, schema, **kwargs):
        return MatchAnalysis(score=50, reasons=[], gaps=[])

    monkeypatch.setattr(llm, "parse", fake_parse)

    m = await job_matching.analyze(
        make_target(), make_job(), make_detail("本職缺請至公司官網投遞履歷")
    )
    assert m.requires_external_apply is True


async def test_analyze_batch_sorts_by_score_desc(monkeypatch):
    scores = iter([40, 90, 70])

    async def fake_parse(prompt, schema, **kwargs):
        return MatchAnalysis(score=next(scores), reasons=[], gaps=[])

    monkeypatch.setattr(llm, "parse", fake_parse)

    pairs = [(make_job(str(i)), make_detail()) for i in range(3)]
    results = await job_matching.analyze_batch(make_target(), pairs)
    assert [r.score for r in results] == [90, 70, 40]
