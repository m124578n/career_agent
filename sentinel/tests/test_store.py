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
