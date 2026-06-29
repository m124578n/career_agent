from career_sentinel import store
from career_sentinel.models import ResumeDiagnosis, ResumeState


def test_load_resume_default_empty(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_resume(conn) == ResumeState()


def test_save_and_load_resume_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_resume(conn, ResumeState(
        resume_text="我的履歷", target_title="後端工程師", expected_salary=60000,
        diagnosis=ResumeDiagnosis(strengths=["熟 Python"], gaps=["缺雲端"]),
    ))
    s = store.load_resume(conn)
    assert s.resume_text == "我的履歷"
    assert s.target_title == "後端工程師"
    assert s.expected_salary == 60000
    assert s.diagnosis.strengths == ["熟 Python"]
    assert s.diagnosis.gaps == ["缺雲端"]
