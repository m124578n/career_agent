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


def test_funnel_104_signals_dont_inflate_match_tailor(tmp_path):
    # 104 直接投遞/面試的職缺沒經過 app 內比對/客製化，不可虛增那些階段。
    from career_sentinel.models import Application, Interview, Snapshot
    conn = _conn(tmp_path)
    snap = Snapshot(
        applications=[
            Application(job_id="1", company="甲", title="後端", status="已讀", applied_at=""),
            Application(job_id="2", company="乙", title="前端", status="已送出", applied_at=""),
        ],
        interviews=[
            Interview(company="丙", job_title="SRE", when="2026-07-10",
                      job_url="https://www.104.com.tw/job/interviewonly"),
        ],
    )
    store.save_snapshot(conn, snap, "2026-07-10T00:00:00")
    r = stats.compute_stats(conn)
    counts = {f.state: f.count for f in r.funnel}
    assert counts["interested"] == 3    # 3 筆都在管道中
    assert counts["matched"] == 0       # 104 投遞不算比對
    assert counts["tailored"] == 0      # 104 投遞不算客製化
    assert counts["applied"] == 2       # 只算真實投遞紀錄；面試職缺不計入投遞
    assert counts["interviewing"] == 1


def test_funnel_manual_match_counts_but_104_applied_does_not(tmp_path):
    # 同一批：有人在 app 內真的比對過 → matched 計 1；純 104 投遞 → 仍不計 matched。
    from career_sentinel.models import Application, Snapshot
    conn = _conn(tmp_path)
    store.save_snapshot(
        conn,
        Snapshot(applications=[
            Application(job_id="p", company="甲", title="後端", status="已讀", applied_at=""),
        ]),
        "2026-07-10T00:00:00",
    )
    store.merge_tracked_job(conn, "p", state="matched")  # 這筆使用者真的比對過
    r = stats.compute_stats(conn)
    counts = {f.state: f.count for f in r.funnel}
    assert counts["matched"] == 1   # 手動比對計入
    assert counts["applied"] == 1   # 也有 104 投遞紀錄


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
