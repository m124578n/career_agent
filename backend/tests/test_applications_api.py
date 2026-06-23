from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.db.repositories import (
    ApplicationRepository,
    MatchRepository,
    SearchRepository,
)
from job_tracker.main import app
from job_tracker.schemas import Job, JobMatch, ResumeTarget


def _seed(db):
    """放一筆 search + match，供加入追蹤。"""
    import asyncio

    async def go():
        sr = SearchRepository(db)
        mr = MatchRepository(db)
        run = await sr.create("dev@local", "python",
                              ResumeTarget(target_title="後端", resume_text="x"))
        job = Job(job_id="1", code="c1", title="工程師", company="某公司",
                  url="https://www.104.com.tw/job/c1")
        await mr.set_match(run.search_id, "dev@local",
                           JobMatch(job=job, score=80, reasons=["r"], gaps=["g"],
                                    cover_letter="信"))
        return run.search_id

    return asyncio.run(go())


def _wire(db):
    app.dependency_overrides[deps.get_application_repo] = lambda: ApplicationRepository(db)
    app.dependency_overrides[deps.get_search_repo] = lambda: SearchRepository(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: MatchRepository(db)


def test_add_list_update_delete_flow():
    db = AsyncMongoMockClient()["test"]
    sid = _seed(db)
    _wire(db)
    try:
        client = TestClient(app)
        added = client.post("/api/applications",
                            json={"search_id": sid, "job_id": "1"})
        listed = client.get("/api/applications")
        patched = client.patch("/api/applications/1", json={"status": "applied"})
        removed = client.delete("/api/applications/1")
        empty = client.get("/api/applications")
    finally:
        app.dependency_overrides.clear()

    assert added.status_code == 200
    assert added.json()["status"] == "to_apply"
    assert added.json()["cover_letter"] == "信"   # 求職信快照
    assert added.json()["job"]["company"] == "某公司"
    assert [a["job_id"] for a in listed.json()] == ["1"]
    assert patched.json()["status"] == "applied"
    assert len(patched.json()["events"]) == 1
    assert removed.status_code == 200
    assert empty.json() == []


def test_add_missing_match_is_404():
    db = AsyncMongoMockClient()["test"]
    sid = _seed(db)
    _wire(db)
    try:
        resp = TestClient(app).post("/api/applications",
                                    json={"search_id": sid, "job_id": "nope"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_add_note_and_set_offer_flow():
    db = AsyncMongoMockClient()["test"]
    sid = _seed(db)
    _wire(db)
    try:
        client = TestClient(app)
        client.post("/api/applications", json={"search_id": sid, "job_id": "1"})
        noted = client.post("/api/applications/1/notes", json={"note": "一面 ok"})
        offered = client.patch("/api/applications/1/offer",
                               json={"salary": "月 60k", "level": "P5"})
    finally:
        app.dependency_overrides.clear()

    assert noted.status_code == 200
    note_events = [e for e in noted.json()["events"] if e["type"] == "note"]
    assert note_events and note_events[0]["note"] == "一面 ok"
    assert offered.status_code == 200
    assert offered.json()["offer"]["salary"] == "月 60k"
    assert offered.json()["offer"]["level"] == "P5"


def test_note_on_missing_app_is_404():
    db = AsyncMongoMockClient()["test"]
    _seed(db)
    _wire(db)
    try:
        resp = TestClient(app).post("/api/applications/nope/notes",
                                    json={"note": "x"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 404
