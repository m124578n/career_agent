from career_sentinel import store
from career_sentinel.models import Application, Message, Snapshot, Viewer


def _snap():
    return Snapshot(
        viewers=[Viewer(company="A", job_title="後端", viewed_at="2026-06-28", raw={"x": 1})],
        applications=[Application(job_id="j1", company="A", title="後端", status="已讀", applied_at="2026-06-20")],
        messages=[Message(thread_id="t1", company="A", last_message="您好", has_interview_invite=True, invite_date="2026-07-01")],
    )


def test_save_and_load_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    sid = store.save_snapshot(conn, _snap(), run_at="2026-06-28T10:00:00")
    loaded = store.load_snapshot(conn, sid)
    assert loaded.viewers[0].company == "A"
    assert loaded.viewers[0].raw == {"x": 1}
    assert loaded.applications[0].job_id == "j1"
    assert loaded.messages[0].has_interview_invite is True
    assert loaded.messages[0].invite_date == "2026-07-01"


def test_latest_two_ids_orders_new_to_old(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    s1 = store.save_snapshot(conn, _snap(), run_at="2026-06-27T10:00:00")
    s2 = store.save_snapshot(conn, _snap(), run_at="2026-06-28T10:00:00")
    assert store.latest_two_ids(conn) == [s2, s1]


def test_snapshot_roundtrip_interviews(tmp_path):
    from career_sentinel import store
    from career_sentinel.models import Interview, Snapshot
    conn = store.connect(str(tmp_path / "db.sqlite"))
    snap = Snapshot(interviews=[
        Interview(company="甲公司", job_title="後端", when="2026-04-07 10:00:00",
                  location="台北", status=10, job_url="https://www.104.com.tw/job/aa1bb",
                  raw={"contactName": "王先生"}),
    ])
    sid = store.save_snapshot(conn, snap, run_at="2026-07-02T09:00:00")
    loaded = store.load_snapshot(conn, sid)
    assert len(loaded.interviews) == 1
    iv = loaded.interviews[0]
    assert iv.company == "甲公司"
    assert iv.when == "2026-04-07 10:00:00"
    assert iv.status == 10
    assert iv.raw["contactName"] == "王先生"


def test_chat_state_roundtrip(tmp_path):
    from career_sentinel.models import ChatMessage, ChatState
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_chat(conn) == ChatState()  # 空 DB 給預設
    st = ChatState(summary="聊過薪資", messages=[
        ChatMessage(role="user", content="期望薪資改 90 萬"),
        ChatMessage(role="assistant", content="好的"),
    ])
    store.save_chat(conn, st)
    assert store.load_chat(conn) == st


def test_preferences_roundtrip(tmp_path):
    from career_sentinel.models import JobPreferences
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_preferences(conn) == JobPreferences()
    prefs = JobPreferences(locations=["台北", "新北"], conditions=["可遠端"], avoid=["博弈"])
    store.save_preferences(conn, prefs)
    assert store.load_preferences(conn) == prefs


def test_memory_roundtrip(tmp_path):
    from career_sentinel.models import MemoryFact, MemoryState
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_memory(conn) == MemoryState()
    mem = MemoryState(facts=[MemoryFact(text="通勤以雙北為主", created_at="2026-07-02T10:00:00")])
    store.save_memory(conn, mem)
    assert store.load_memory(conn) == mem


def test_old_db_gains_new_tables(tmp_path):
    # 既有 DB（重連即跑 CREATE IF NOT EXISTS）也長得出新表 → 加法式遷移
    from career_sentinel.models import ChatState
    p = tmp_path / "db.sqlite"
    store.connect(p).close()
    conn = store.connect(p)
    assert store.load_chat(conn) == ChatState()


def test_dismissed_interviews_roundtrip(tmp_path):
    from career_sentinel.models import DismissedInterviews
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_dismissed(conn) == DismissedInterviews()
    store.save_dismissed(conn, DismissedInterviews(keys=["甲|後端|2026-04-07 10:00:00"]))
    assert store.load_dismissed(conn).keys == ["甲|後端|2026-04-07 10:00:00"]


def test_company_research_roundtrip(tmp_path):
    from career_sentinel.models import CompanyResearch, ResearchSource
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_research(conn, "台積電") is None
    r = CompanyResearch(
        company="台積電", summary="整體評價正面", pros=["福利好"], cons=["工時長"],
        salary_notes="高於同業", interview_notes="流程長", risk_level="low",
        sources=[ResearchSource(title="面試趣", url="https://interview.tw/x")],
        researched_at="2026-07-03T10:00:00",
    )
    store.save_research(conn, r)
    assert store.load_research(conn, "台積電") == r
    r2 = r.model_copy(update={"summary": "更新後"})
    store.save_research(conn, r2)  # 同公司覆寫
    assert store.load_research(conn, "台積電").summary == "更新後"


def test_company_research_risk_whitelist(tmp_path):
    from career_sentinel.models import CompanyResearch
    assert CompanyResearch(risk_level="weird").risk_level == "mid"
    assert CompanyResearch(risk_level="high").risk_level == "high"
