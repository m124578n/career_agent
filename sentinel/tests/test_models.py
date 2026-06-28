from career_sentinel.models import (
    Application, Diff, Message, Snapshot, StatusChange, Viewer,
)


def test_models_build_with_defaults():
    v = Viewer(company="A", job_title="後端", viewed_at="2026-06-28")
    assert v.raw == {}
    a = Application(job_id="1", company="A", title="後端", status="已讀", applied_at="2026-06-20")
    m = Message(thread_id="t1", company="A", last_message="您好")
    assert m.has_interview_invite is False and m.invite_date is None
    snap = Snapshot(viewers=[v], applications=[a], messages=[m])
    assert len(snap.viewers) == 1


def test_diff_is_empty():
    assert Diff().is_empty() is True
    d = Diff(new_viewers=[Viewer(company="A", job_title="x", viewed_at="t")])
    assert d.is_empty() is False


def test_status_change_holds_old_and_new():
    a = Application(job_id="1", company="A", title="x", status="邀請面試", applied_at="t")
    sc = StatusChange(application=a, old_status="已讀", new_status="邀請面試")
    assert sc.old_status == "已讀" and sc.new_status == "邀請面試"
