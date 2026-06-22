# backend/tests/test_schemas.py
from job_tracker.schemas import (
    Application,
    ApplicationEvent,
    ApplicationStatus,
    Job,
    ResumeTarget,
    SearchRun,
)


def _job() -> Job:
    return Job(job_id="1", code="abc", title="工程師", company="某公司",
               url="https://www.104.com.tw/job/abc")


def test_search_run_defaults():
    run = SearchRun(search_id="s1", user="u1", keyword="python",
                    target=ResumeTarget(target_title="後端", resume_text="x"))
    assert run.next_offset == 0
    assert run.count == 0
    assert run.created_at is not None


def test_application_defaults_to_to_apply():
    app = Application(user="u1", job_id="1", job=_job(), source_search_id="s1")
    assert app.status == ApplicationStatus.TO_APPLY
    assert app.events == []
    assert app.cover_letter is None


def test_application_status_values():
    assert [s.value for s in ApplicationStatus] == [
        "to_apply", "applied", "interviewing", "offer", "closed"
    ]


def test_application_event_shape():
    ev = ApplicationEvent(type="status", note="→ applied")
    assert ev.type == "status"
    assert ev.note == "→ applied"
