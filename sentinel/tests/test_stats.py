from datetime import datetime, timedelta

from career_sentinel import stats, store


def _conn(tmp_path):
    return store.connect(str(tmp_path / "db.sqlite"))


def test_funnel_reached_is_monotonic(tmp_path):
    conn = _conn(tmp_path)
    store.merge_tracked_job(conn, "a", state="interested")
    store.merge_tracked_job(conn, "b", state="matched")
    store.set_tracked_state(conn, "c", "offer")
    r = stats.compute_stats(conn)
    counts = {f.state: f.count for f in r.funnel}
    # reached：interested 計全部非 rejected(3)、matched≥2(2)、offer(1)
    assert counts["interested"] == 3
    assert counts["matched"] == 2
    assert counts["offer"] == 1
    # 單調遞減
    seq = [f.count for f in r.funnel]
    assert seq == sorted(seq, reverse=True)


def test_rejected_excluded_from_funnel(tmp_path):
    conn = _conn(tmp_path)
    store.merge_tracked_job(conn, "a", state="interested")
    store.set_tracked_state(conn, "b", "rejected")
    r = stats.compute_stats(conn)
    assert r.rejected_count == 1
    assert {f.state: f.count for f in r.funnel}["interested"] == 1  # rejected 不計入


def test_conversions_and_zero_denominator(tmp_path):
    conn = _conn(tmp_path)
    # 只有一個 interested → applied 分母 0
    store.merge_tracked_job(conn, "a", state="interested")
    r = stats.compute_stats(conn)
    assert r.conversions.applied_to_interview is None
    assert r.conversions.interested_to_offer == 0  # 分母 1、offer 0


def test_dwell_median_from_events(tmp_path):
    conn = _conn(tmp_path)
    # 手動塞事件：interested 停 2 天後進 matched
    store.append_state_event(conn, "x", "interested", "2026-07-01T00:00:00")
    store.append_state_event(conn, "x", "matched", "2026-07-03T00:00:00")
    store.append_state_event(conn, "y", "interested", "2026-07-01T00:00:00")
    store.append_state_event(conn, "y", "matched", "2026-07-05T00:00:00")  # 停 4 天
    r = stats.compute_stats(conn)
    d = {x.state: x for x in r.dwell}
    assert d["interested"].sample == 2
    assert d["interested"].median_days == 3   # (2,4) 中位數 3


def test_stale_over_threshold_excludes_terminal(tmp_path):
    conn = _conn(tmp_path)
    old = (datetime.now() - timedelta(days=20)).isoformat(timespec="seconds")
    from career_sentinel.models import TrackedJob
    store.upsert_tracked_job(conn, TrackedJob(code="s", company="甲", title="後端",
                                              state="interested", created_at=old, updated_at=old))
    store.upsert_tracked_job(conn, TrackedJob(code="o", state="offer", created_at=old, updated_at=old))
    r = stats.compute_stats(conn)
    codes = [j.code for j in r.stale]
    assert "s" in codes and "o" not in codes  # 終端狀態排除
    assert next(j for j in r.stale if j.code == "s").days_since_update >= 20
