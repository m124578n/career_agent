from career_sentinel.diff import compute_diff, diff_against_last
from career_sentinel.models import Application, Message, Snapshot, Viewer
from career_sentinel import store


def test_first_run_everything_is_new():
    cur = Snapshot(
        viewers=[Viewer(company="A", job_title="後端", viewed_at="t")],
        messages=[Message(thread_id="t1", company="A", last_message="hi", has_interview_invite=True)],
    )
    d = compute_diff(None, cur)
    assert len(d.new_viewers) == 1
    assert len(d.new_invites) == 1
    assert len(d.new_messages) == 1


def test_new_viewer_detected():
    prev = Snapshot(viewers=[Viewer(company="A", job_title="後端", viewed_at="t")])
    cur = Snapshot(viewers=[
        Viewer(company="A", job_title="後端", viewed_at="t"),
        Viewer(company="B", job_title="前端", viewed_at="t2"),
    ])
    d = compute_diff(prev, cur)
    assert [v.company for v in d.new_viewers] == ["B"]


def test_status_change_detected():
    prev = Snapshot(applications=[Application(job_id="j1", company="A", title="x", status="已讀", applied_at="t")])
    cur = Snapshot(applications=[Application(job_id="j1", company="A", title="x", status="邀請面試", applied_at="t")])
    d = compute_diff(prev, cur)
    assert len(d.status_changes) == 1
    assert d.status_changes[0].old_status == "已讀"
    assert d.status_changes[0].new_status == "邀請面試"


def test_new_invite_only_when_flag_flips_true():
    prev = Snapshot(messages=[Message(thread_id="t1", company="A", last_message="hi", has_interview_invite=False)])
    cur = Snapshot(messages=[Message(thread_id="t1", company="A", last_message="要約面試", has_interview_invite=True, invite_date="2026-07-01")])
    d = compute_diff(prev, cur)
    assert len(d.new_invites) == 1
    assert len(d.new_messages) == 1  # last_message 也變了


def test_no_change_is_empty():
    snap = Snapshot(applications=[Application(job_id="j1", company="A", title="x", status="已讀", applied_at="t")])
    assert compute_diff(snap, snap).is_empty()


def test_no_repeat_invite_when_already_true():
    prev = Snapshot(messages=[Message(thread_id="t1", company="A", last_message="hi", has_interview_invite=True)])
    cur = Snapshot(messages=[Message(thread_id="t1", company="A", last_message="hi", has_interview_invite=True)])
    d = compute_diff(prev, cur)
    assert len(d.new_invites) == 0


def test_diff_against_last_with_multiple_snapshots(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    # Save snapshot A with one viewer
    snap_a = Snapshot(viewers=[Viewer(company="A", job_title="後端", viewed_at="t")])
    sid_a = store.save_snapshot(conn, snap_a, run_at="2026-06-27T10:00:00")
    # Save snapshot B that adds a second viewer
    snap_b = Snapshot(viewers=[
        Viewer(company="A", job_title="後端", viewed_at="t"),
        Viewer(company="B", job_title="前端", viewed_at="t2"),
    ])
    sid_b = store.save_snapshot(conn, snap_b, run_at="2026-06-28T10:00:00")
    # Call diff_against_last with B's id
    d = diff_against_last(conn, sid_b)
    # Assert exactly one new_viewer (the added one)
    assert len(d.new_viewers) == 1
    assert d.new_viewers[0].company == "B"


def test_diff_against_last_single_snapshot_first_run(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    # Save only ONE snapshot
    snap = Snapshot(viewers=[Viewer(company="A", job_title="後端", viewed_at="t")])
    sid = store.save_snapshot(conn, snap, run_at="2026-06-28T10:00:00")
    # Call diff_against_last with the single snapshot's id
    d = diff_against_last(conn, sid)
    # Assert it treats everything as new (first-run path: the viewer appears in new_viewers)
    assert len(d.new_viewers) == 1
    assert d.new_viewers[0].company == "A"


def test_new_application_is_not_a_status_change():
    prev = Snapshot()
    cur = Snapshot(applications=[Application(job_id="j9", company="A", title="x", status="已讀", applied_at="t")])
    d = compute_diff(prev, cur)
    assert len(d.status_changes) == 0
