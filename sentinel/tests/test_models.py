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


def test_recommended_job_defaults():
    from career_sentinel.models import RecommendedJob
    j = RecommendedJob(code="aa1bb", url="https://www.104.com.tw/job/aa1bb")
    assert j.code == "aa1bb"
    assert j.title == "" and j.company == "" and j.salary == ""
    assert j.is_watched is False


def test_change_counts_total():
    from career_sentinel.models import ChangeCounts
    c = ChangeCounts(new_viewers=2, status_changes=1, new_messages=3, new_invites=1)
    assert c.total == 7

def test_change_counts_defaults_zero():
    from career_sentinel.models import ChangeCounts
    assert ChangeCounts().total == 0

def test_change_counts_from_diff():
    from career_sentinel.models import (
        Application, ChangeCounts, Diff, Message, StatusChange, Viewer,
    )
    d = Diff(
        new_viewers=[Viewer(company="A", job_title="x", viewed_at="t")],
        status_changes=[StatusChange(
            application=Application(job_id="1", company="B", title="t", status="已讀", applied_at="d"),
            old_status="已送出", new_status="已讀")],
        new_messages=[Message(thread_id="m1", company="C", last_message="hi")],
        new_invites=[Message(thread_id="m1", company="C", last_message="hi", has_interview_invite=True)],
    )
    c = ChangeCounts.from_diff(d)
    assert (c.new_viewers, c.status_changes, c.new_messages, c.new_invites) == (1, 1, 1, 1)
    assert c.total == 4
