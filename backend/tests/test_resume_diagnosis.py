from job_tracker import llm
from job_tracker.schemas import ResumeDiagnosis, ResumeTarget
from job_tracker.services import resume_diagnosis


def make_target() -> ResumeTarget:
    return ResumeTarget(
        target_title="資深後端工程師",
        expected_salary=80000,
        resume_text="3 年 Python 經驗，做過 FastAPI 與 MongoDB",
    )


async def test_diagnose_builds_diagnosis_from_llm(monkeypatch):
    async def fake_parse(prompt, schema, **kwargs):
        assert schema is ResumeDiagnosis
        # prompt 應帶入目標職位、薪資與履歷內容
        assert "資深後端工程師" in prompt
        assert "80000" in prompt
        assert "FastAPI" in prompt
        return ResumeDiagnosis(
            strengths=["後端框架經驗扎實"],
            gaps=["缺乏團隊領導經驗"],
        )

    monkeypatch.setattr(llm, "parse", fake_parse)

    result = await resume_diagnosis.diagnose(make_target())
    assert result.strengths == ["後端框架經驗扎實"]
    assert result.gaps == ["缺乏團隊領導經驗"]
