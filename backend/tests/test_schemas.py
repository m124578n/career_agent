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
    assert run.next_page == 1
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


def test_jobmatch_candidate_defaults():
    from job_tracker.schemas import Job, JobMatch
    job = Job(job_id="1", code="c1", title="t", company="co", url="https://x/1")
    m = JobMatch(job=job)  # candidate 階段：還沒有分數
    assert m.score == 0
    assert m.reasons == [] and m.gaps == []
    assert m.status == "done"      # 預設值，向後相容既有資料
    assert m.relevant is True


def test_searchrun_area_and_next_page():
    from job_tracker.schemas import ResumeTarget, SearchRun
    run = SearchRun(search_id="s1", user="u1", keyword="python",
                    target=ResumeTarget(target_title="後端", resume_text="x"))
    assert run.area is None
    assert run.next_page == 1
    assert run.count == 0


def test_application_offer_defaults_none():
    from job_tracker.schemas import Application, Job
    job = Job(job_id="1", code="c1", title="工程師", company="某公司",
              url="https://www.104.com.tw/job/c1")
    app = Application(user="u1", job_id="1", job=job, source_search_id="s1")
    assert app.offer is None


def test_offer_info_all_optional():
    from job_tracker.schemas import OfferInfo
    o = OfferInfo()
    assert o.salary is None and o.accepted is None
    o2 = OfferInfo(salary="月 60k＋年終 2 個月", accepted=True)
    assert o2.salary == "月 60k＋年終 2 個月"
    assert o2.accepted is True


def test_match_analysis_benefits_defaults_empty():
    from job_tracker.schemas import MatchAnalysis
    a = MatchAnalysis(score=80, reasons=[], gaps=[])
    assert a.benefits == []
    a2 = MatchAnalysis(score=80, reasons=[], gaps=[], benefits=["特休優於法令"])
    assert a2.benefits == ["特休優於法令"]


def test_jobmatch_benefits_defaults_empty():
    from job_tracker.schemas import Job, JobMatch
    job = Job(job_id="1", code="c1", title="t", company="co",
              url="https://www.104.com.tw/job/c1")
    m = JobMatch(job=job)
    assert m.benefits == []
