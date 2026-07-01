# career-sentinel SP7 面試擷取 + 加入 Google 日曆 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 擷取 104 面試場次（公司/職缺/確切時間/地點）併入既有 scrape，在儀表板列「即將到來的面試」，每筆一顆預填 Google 日曆連結。

**Architecture:** 新 reader `scraper/interviews.py` 打登入態 `api/interviews`（回結構化面試，含 `interviewTime` 確切時間），併入既有 scrape session/Snapshot/store（面試為第 4 類資料）。純函式 `calendar_link.build_gcal_link` 產生 Google Calendar 預填 URL（零 OAuth）。儀表板加「即將到來的面試」區塊。

**Tech Stack:** Python 3.12 / Pydantic v2 / rebrowser-playwright（登入態 headful）/ SQLite / FastAPI / React 18 + Vite + Mantine 7。

## Global Constraints

- 面試端點（實機擷取確認）：`GET https://pda.104.com.tw/api/interviews?page=1&pageSize=20`，登入態（與其他 pda reader 同 `page.request.get`）。回 `{"data": [interview...], "metadata": {...}}`。
- 面試欄位（實機確認）：`custName`→company、`jobName`→job_title、`interviewTime`→when（格式 `YYYY-MM-DD HH:MM:SS`）、`address`→location、`jobUrl`→job_url、`status`→status（**數字碼，無明確 legend**——options 端點的字串 value coming/pending/... 對不上數字，故 status 存 raw、UI 不顯示 badge）、`chatroomId`/`contactName`/`contactTel` 存 raw。
- Google 日曆連結：`https://calendar.google.com/calendar/render?action=TEMPLATE&text=面試：<公司>&dates=<起>/<迄>&details=職缺：<職缺>\n<job_url>&location=<地點>`，全參數 `urlencode`；`when` 可解析 → `dates=YYYYMMDDTHHMMSS/起+1h`；`when` 空/不可解析 → **不帶 dates**（fallback，使用者自填時間）。預設面試時長 1 小時。
- 面試併入既有 Snapshot（第 4 類）；**不進 diff、不進 SP6「N 筆新動態」通知**（新面試已由既有 message `has_interview_invite`→`new_invites` 粗略涵蓋）。
- 只做預填連結（非 Calendar API）。stateless 之外的持久化沿用既有 snapshot。後端只綁 127.0.0.1。
- 既有 142 測試不得回歸。前端須 `npm run build` 通過。
- pytest / npm 從對應目錄執行：後端 `cd sentinel && uv run pytest`；前端 `cd sentinel/web/frontend && npm run build`。

---

### Task 1: `Interview` model + `scraper/interviews.py`（解析 + 擷取）

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（新增 `Interview`、`Snapshot` 加 `interviews`）
- Create: `sentinel/src/career_sentinel/scraper/interviews.py`
- Create: `sentinel/tests/fixtures/interviews.json`（去識別化）
- Create: `sentinel/tests/test_parse_interviews.py`

**Interfaces:**
- Produces: `Interview(company:str="", job_title:str="", when:str="", location:str="", status:int|None=None, job_url:str="", raw:dict)`；`Snapshot.interviews: list[Interview]`；`INTERVIEWS_URL:str`、`parse_interviews(payload:dict)->list[Interview]`（純）、`fetch_interviews(page)->list[Interview]`（登入態、不單測）。

- [ ] **Step 1: 新增 model**

在 `models.py`：`Snapshot` 加一欄位（其餘不動）：

```python
class Snapshot(BaseModel):
    viewers: list[Viewer] = Field(default_factory=list)
    applications: list[Application] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    interviews: list["Interview"] = Field(default_factory=list)
```

在 `models.py` 末尾加：

```python
class Interview(BaseModel):
    company: str = ""
    job_title: str = ""
    when: str = ""
    location: str = ""
    status: int | None = None
    job_url: str = ""
    raw: dict = Field(default_factory=dict)
```

（`Snapshot` 用 forward ref `"Interview"`，因 `Interview` 定義在後；Pydantic v2 會自動解析同模組 forward ref。若跑測試出現未解析錯誤，在 `Interview` 定義後加 `Snapshot.model_rebuild()`。）

- [ ] **Step 2: 建去識別化 fixture**

Create `sentinel/tests/fixtures/interviews.json`：

```json
{
  "data": [
    {
      "seq": 1, "eventId": "e1", "msgId": "m1", "chatroomId": "aa1bb",
      "custName": "範例科技股份有限公司", "custNo": "c1d2e3",
      "jobName": "資深後端工程師", "jobNo": "11", "jobUrl": "https://www.104.com.tw/job/aa1bb",
      "contactName": "王先生", "contactTel": "02-1234-5678",
      "address": "台北市內湖區範例路 1 號", "interviewTime": "2026-04-07 10:00:00",
      "status": 10, "active": 5
    },
    {
      "seq": 2, "eventId": "e2", "msgId": "m2", "chatroomId": "cc3dd",
      "custName": "範例雲端有限公司", "custNo": "f4g5h6",
      "jobName": "資料工程師", "jobNo": "22", "jobUrl": "https://www.104.com.tw/job/cc3dd",
      "contactName": "李小姐", "contactTel": "03-8765-4321",
      "address": "新竹市東區範例街 2 號", "interviewTime": "2026-04-09 13:30:00",
      "status": 1, "active": 3
    }
  ],
  "metadata": { "pagination": { "count": 2, "total": 2, "currentPage": 1, "lastPage": 1 } }
}
```

- [ ] **Step 3: 寫解析失敗測試**

Create `sentinel/tests/test_parse_interviews.py`：

```python
import json
from pathlib import Path

from career_sentinel.scraper.interviews import parse_interviews

FIX = Path(__file__).parent / "fixtures" / "interviews.json"


def test_parse_interviews_maps_fields():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    ivs = parse_interviews(data)
    assert len(ivs) == 2
    iv = ivs[0]
    assert iv.company == "範例科技股份有限公司"
    assert iv.job_title == "資深後端工程師"
    assert iv.when == "2026-04-07 10:00:00"
    assert iv.location == "台北市內湖區範例路 1 號"
    assert iv.job_url == "https://www.104.com.tw/job/aa1bb"
    assert iv.status == 10
    assert iv.raw["contactName"] == "王先生"


def test_parse_interviews_skips_bad_entries():
    payload = {"data": [
        "壞字串",
        {"custName": "甲公司", "jobName": "工程師", "interviewTime": "2026-05-01 09:00:00",
         "address": "台北", "jobUrl": "u", "status": 1},
    ]}
    ivs = parse_interviews(payload)
    assert len(ivs) == 1
    assert ivs[0].company == "甲公司"


def test_parse_interviews_empty():
    assert parse_interviews({"data": []}) == []
```

- [ ] **Step 4: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_parse_interviews.py -q`
Expected: FAIL（ModuleNotFoundError: career_sentinel.scraper.interviews）

- [ ] **Step 5: 實作 `scraper/interviews.py`**

Create `sentinel/src/career_sentinel/scraper/interviews.py`：

```python
from __future__ import annotations

from ..models import Interview

INTERVIEWS_URL = "https://pda.104.com.tw/api/interviews?page=1&pageSize=20"


def parse_interviews(payload: dict) -> list[Interview]:
    """把 104 面試端點 JSON 解析成 Interview；壞筆（非 dict）略過、不炸整批。"""
    out: list[Interview] = []
    for item in payload.get("data", []) or []:
        if not isinstance(item, dict):
            continue
        out.append(
            Interview(
                company=(item.get("custName") or "").strip(),
                job_title=(item.get("jobName") or "").strip(),
                when=(item.get("interviewTime") or "").strip(),
                location=(item.get("address") or "").strip(),
                status=item.get("status") if isinstance(item.get("status"), int) else None,
                job_url=(item.get("jobUrl") or "").strip(),
                raw=item,
            )
        )
    return out


def fetch_interviews(page) -> list[Interview]:
    """需已登入且已取得 pda host 的 Cloudflare clearance。需真瀏覽器、不單測。"""
    resp = page.request.get(INTERVIEWS_URL)
    if not resp.ok:
        raise RuntimeError(f"interviews HTTP {resp.status}")
    return parse_interviews(resp.json())
```

- [ ] **Step 6: 跑測試確認通過 + 全測試無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: PASS（全綠；含新增 3 個）

- [ ] **Step 7: Commit**

```bash
cd sentinel && git add src/career_sentinel/models.py src/career_sentinel/scraper/interviews.py tests/fixtures/interviews.json tests/test_parse_interviews.py
git commit -m "feat(sentinel): Interview model + scraper/interviews（面試場次擷取）（SP7）"
```

---

### Task 2: `calendar_link.build_gcal_link`

**Files:**
- Create: `sentinel/src/career_sentinel/calendar_link.py`
- Test: `sentinel/tests/test_calendar_link.py`

**Interfaces:**
- Consumes: `Interview`（Task 1）。
- Produces: `build_gcal_link(iv: Interview) -> str`。

- [ ] **Step 1: 寫失敗測試**

Create `sentinel/tests/test_calendar_link.py`：

```python
from urllib.parse import parse_qs, urlparse

from career_sentinel.calendar_link import build_gcal_link
from career_sentinel.models import Interview


def test_gcal_link_with_time():
    iv = Interview(company="甲公司", job_title="後端工程師", when="2026-04-07 10:00:00",
                   location="台北市內湖區", job_url="https://www.104.com.tw/job/aa1bb")
    url = build_gcal_link(iv)
    q = parse_qs(urlparse(url).query)
    assert q["action"] == ["TEMPLATE"]
    assert q["text"] == ["面試：甲公司"]
    assert q["dates"] == ["20260407T100000/20260407T110000"]  # 起 / 起+1h
    assert q["location"] == ["台北市內湖區"]
    assert "後端工程師" in q["details"][0]
    assert "https://www.104.com.tw/job/aa1bb" in q["details"][0]


def test_gcal_link_without_time_omits_dates():
    iv = Interview(company="乙公司", job_title="PM", when="", location="新竹")
    url = build_gcal_link(iv)
    q = parse_qs(urlparse(url).query)
    assert "dates" not in q
    assert q["text"] == ["面試：乙公司"]


def test_gcal_link_unparseable_time_omits_dates():
    iv = Interview(company="丙", job_title="x", when="待通知")
    q = parse_qs(urlparse(build_gcal_link(iv)).query)
    assert "dates" not in q
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_calendar_link.py -q`
Expected: FAIL（ModuleNotFoundError: career_sentinel.calendar_link）

- [ ] **Step 3: 實作 `calendar_link.py`**

Create `sentinel/src/career_sentinel/calendar_link.py`：

```python
from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlencode

from .models import Interview

_RENDER = "https://calendar.google.com/calendar/render"
_IN_FMT = "%Y-%m-%d %H:%M:%S"
_OUT_FMT = "%Y%m%dT%H%M%S"


def _to_dates(when: str) -> str | None:
    """'2026-04-07 10:00:00' → '20260407T100000/20260407T110000'（起/起+1h）；不可解析回 None。"""
    try:
        start = datetime.strptime(when, _IN_FMT)
    except (ValueError, TypeError):
        return None
    end = start + timedelta(hours=1)
    return f"{start.strftime(_OUT_FMT)}/{end.strftime(_OUT_FMT)}"


def build_gcal_link(iv: Interview) -> str:
    """產生 Google Calendar 預填新增事件連結（零 OAuth）。無/不可解析時間 → 不帶 dates。"""
    details = f"職缺：{iv.job_title}"
    if iv.job_url:
        details += f"\n{iv.job_url}"
    params = {
        "action": "TEMPLATE",
        "text": f"面試：{iv.company}",
        "details": details,
    }
    if iv.location:
        params["location"] = iv.location
    dates = _to_dates(iv.when)
    if dates:
        params["dates"] = dates
    return f"{_RENDER}?{urlencode(params)}"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_calendar_link.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
cd sentinel && git add src/career_sentinel/calendar_link.py tests/test_calendar_link.py
git commit -m "feat(sentinel): build_gcal_link（面試→Google 日曆預填連結）（SP7）"
```

---

### Task 3: `store` 持久化 interviews

**Files:**
- Modify: `sentinel/src/career_sentinel/store.py`（schema + save_snapshot + load_snapshot）
- Test: `sentinel/tests/test_store.py`

**Interfaces:**
- Consumes: `Interview`/`Snapshot.interviews`（Task 1）。
- Produces: snapshot 存讀 round-trip 保留 interviews。

- [ ] **Step 1: 寫失敗測試**

在 `sentinel/tests/test_store.py` 末尾加：

```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_store.py::test_snapshot_roundtrip_interviews -q`
Expected: FAIL（load 回的 interviews 為空 / 無 interviews table）

- [ ] **Step 3: 改 `store.py`**

`store.py` 頂部 import 加 `Interview`：把 `from .models import Application, Message, ResumeState, Settings, Snapshot, Viewer` 改為 `from .models import Application, Interview, Message, ResumeState, Settings, Snapshot, Viewer`。

`_SCHEMA` 在 `messages` table 之後加：

```python
CREATE TABLE IF NOT EXISTS interviews (
    snapshot_id INTEGER, company TEXT, job_title TEXT, interview_time TEXT,
    location TEXT, status INTEGER, job_url TEXT, raw_json TEXT
);
```

`save_snapshot` 在 messages 那段 `executemany` 之後、`conn.commit()` 之前加：

```python
    conn.executemany(
        "INSERT INTO interviews VALUES (?,?,?,?,?,?,?,?)",
        [(sid, iv.company, iv.job_title, iv.when, iv.location, iv.status, iv.job_url, json.dumps(iv.raw, ensure_ascii=False)) for iv in snapshot.interviews],
    )
```

`load_snapshot` 在 messages 那段之後加，並把 `return` 改為帶 interviews：

```python
    interviews = [
        Interview(company=c, job_title=t, when=w, location=lo, status=s, job_url=ju, raw=json.loads(rj))
        for c, t, w, lo, s, ju, rj in conn.execute(
            "SELECT company, job_title, interview_time, location, status, job_url, raw_json FROM interviews WHERE snapshot_id=?", (snapshot_id,)
        )
    ]
    return Snapshot(viewers=viewers, applications=applications, messages=messages, interviews=interviews)
```

- [ ] **Step 4: 跑測試確認通過 + 全測試無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: PASS（全綠）

- [ ] **Step 5: Commit**

```bash
cd sentinel && git add src/career_sentinel/store.py tests/test_store.py
git commit -m "feat(sentinel): snapshot 持久化 interviews（SP7）"
```

---

### Task 4: 併入 scrape reader + carry_forward 第 4 欄位

**Files:**
- Modify: `sentinel/src/career_sentinel/scraper/real.py`（readers 加 interviews）
- Modify: `sentinel/src/career_sentinel/cli.py`（`_carry_forward` 加 interviews）
- Test: `sentinel/tests/test_real_scrape.py`、`sentinel/tests/test_cli.py`

**Interfaces:**
- Consumes: `fetch_interviews`（Task 1）、`Snapshot.interviews`（Task 1）。
- Produces: `scrape` 收集 interviews 進 Snapshot；`_carry_forward` 對 interviews 沿用上次。

- [ ] **Step 1: 寫 real.scrape 失敗測試**

在 `sentinel/tests/test_real_scrape.py` 末尾加（monkeypatch 各 reader 為假、驗證 interviews 進 snapshot）：

```python
def test_scrape_collects_interviews(monkeypatch):
    from career_sentinel.scraper import real
    from career_sentinel.models import Interview
    monkeypatch.setattr(real, "fetch_viewers", lambda page: [])
    monkeypatch.setattr(real, "fetch_applications", lambda page: [])
    monkeypatch.setattr(real, "fetch_messages", lambda page: [])
    monkeypatch.setattr(real, "fetch_interviews", lambda page: [Interview(company="甲", when="2026-04-07 10:00:00")])
    snap, failed = real.scrape(page=object())
    assert failed == set()
    assert len(snap.interviews) == 1
    assert snap.interviews[0].company == "甲"


def test_scrape_interviews_failure_recorded(monkeypatch):
    from career_sentinel.scraper import real
    monkeypatch.setattr(real, "fetch_viewers", lambda page: [])
    monkeypatch.setattr(real, "fetch_applications", lambda page: [])
    monkeypatch.setattr(real, "fetch_messages", lambda page: [])
    def boom(page): raise RuntimeError("interviews HTTP 500")
    monkeypatch.setattr(real, "fetch_interviews", boom)
    snap, failed = real.scrape(page=object())
    assert "interviews" in failed
```

（若既有 `test_real_scrape.py` 已有 monkeypatch reader 的 helper，沿用其風格；上面假設 reader 是 `real` 模組層級名稱，與既有 `from .viewers import fetch_viewers` 等一致——它們在 `real.py` 命名空間可被 monkeypatch。）

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_real_scrape.py -q`
Expected: FAIL（AttributeError: real 無 fetch_interviews / snap 無 interviews）

- [ ] **Step 3: 改 `real.py`**

`real.py` 頂部 import 加：`from .interviews import fetch_interviews`。
`scrape` 改為（readers 加 interviews、collected 加、Snapshot 帶）：

```python
def scrape(page) -> tuple[Snapshot, set[str]]:
    """逐讀取器抓取；單一失敗只記進 failed、不中斷其他。"""
    readers = (
        ("viewers", fetch_viewers),
        ("applications", fetch_applications),
        ("messages", fetch_messages),
        ("interviews", fetch_interviews),
    )
    collected: dict[str, list] = {"viewers": [], "applications": [], "messages": [], "interviews": []}
    failed: set[str] = set()
    for name, fn in readers:
        try:
            collected[name] = fn(page)
        except Exception:
            failed.add(name)
    snapshot = Snapshot(
        viewers=collected["viewers"],
        applications=collected["applications"],
        messages=collected["messages"],
        interviews=collected["interviews"],
    )
    return snapshot, failed
```

- [ ] **Step 4: 寫 carry_forward 失敗測試**

在 `sentinel/tests/test_cli.py` 末尾加：

```python
def test_carry_forward_interviews(tmp_path):
    from career_sentinel import cli, store
    from career_sentinel.models import Interview, Snapshot
    conn = store.connect(str(tmp_path / "db.sqlite"))
    prev = Snapshot(interviews=[Interview(company="舊公司", when="2026-04-01 09:00:00")])
    store.save_snapshot(conn, prev, run_at="2026-07-01T09:00:00")
    # 這次 interviews 抓取失敗 → 應沿用上次
    fresh = Snapshot(interviews=[])
    merged = cli._carry_forward(conn, fresh, {"interviews"})
    assert len(merged.interviews) == 1
    assert merged.interviews[0].company == "舊公司"
```

- [ ] **Step 5: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_cli.py::test_carry_forward_interviews -q`
Expected: FAIL（merged.interviews 為空——carry_forward 未含 interviews）

- [ ] **Step 6: 改 `cli._carry_forward`**

`cli.py` 的 `_carry_forward` 的 `return Snapshot(...)` 加 interviews 欄位：

```python
    return Snapshot(
        viewers=prev.viewers if "viewers" in failed else snapshot.viewers,
        applications=prev.applications if "applications" in failed else snapshot.applications,
        messages=prev.messages if "messages" in failed else snapshot.messages,
        interviews=prev.interviews if "interviews" in failed else snapshot.interviews,
    )
```

- [ ] **Step 7: 跑測試確認通過 + 全測試無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: PASS（全綠）

- [ ] **Step 8: Commit**

```bash
cd sentinel && git add src/career_sentinel/scraper/real.py src/career_sentinel/cli.py tests/test_real_scrape.py tests/test_cli.py
git commit -m "feat(sentinel): scrape 併入 interviews reader + carry_forward 第 4 欄位（SP7）"
```

---

### Task 5: `/api/snapshot` 輸出 interviews + gcal_link

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`（`_snapshot_payload` 加 interviews）
- Test: `sentinel/tests/test_web_app.py`

**Interfaces:**
- Consumes: `build_gcal_link`（Task 2）、`Snapshot.interviews`（Task 1）。
- Produces: `GET /api/snapshot` 回傳多一鍵 `interviews`，每筆 `{company, job_title, when, location, job_url, gcal_link}`，按 `when` 升冪（空的排後）。

- [ ] **Step 1: 寫 API 失敗測試**

在 `sentinel/tests/test_web_app.py` 末尾加：

```python
def test_snapshot_exposes_interviews_with_gcal_link(tmp_path):
    from fastapi.testclient import TestClient
    from career_sentinel import store
    from career_sentinel.models import Interview, Snapshot
    from career_sentinel.web.app import create_app
    db = str(tmp_path / "t.db")
    conn = store.connect(db)
    store.save_snapshot(conn, Snapshot(interviews=[
        Interview(company="乙公司", job_title="PM", when="2026-04-09 13:30:00", location="新竹", job_url="u2"),
        Interview(company="甲公司", job_title="後端", when="2026-04-07 10:00:00", location="台北", job_url="u1"),
    ]), run_at="2026-07-02T09:00:00")
    client = TestClient(create_app(db_path=db))
    r = client.get("/api/snapshot")
    assert r.status_code == 200
    ivs = r.json()["interviews"]
    assert len(ivs) == 2
    assert ivs[0]["when"] == "2026-04-07 10:00:00"  # 按 when 升冪，早的在前
    assert ivs[0]["company"] == "甲公司"
    assert "calendar.google.com" in ivs[0]["gcal_link"]
    assert "dates=" in ivs[0]["gcal_link"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_app.py::test_snapshot_exposes_interviews_with_gcal_link -q`
Expected: FAIL（KeyError 'interviews'）

- [ ] **Step 3: 改 `_snapshot_payload`**

`web/app.py` 頂部 import 加 `calendar_link`：把 `from .. import config, diagnosis, diff, digest, jobfetch, match, resume, store, watch` 改為加入 `calendar_link`（如 `from .. import calendar_link, config, diagnosis, diff, digest, jobfetch, match, resume, store, watch`）。

在 `_snapshot_payload` 的 return dict 加一鍵（在既有 `messages` 之後、`digest` 之前或任意位置）：

```python
        "interviews": [
            {
                "company": iv.company, "job_title": iv.job_title, "when": iv.when,
                "location": iv.location, "job_url": iv.job_url,
                "gcal_link": calendar_link.build_gcal_link(iv),
            }
            for iv in sorted(snap.interviews, key=lambda iv: (iv.when == "", iv.when))
        ],
```

（`sorted` 的 key `(iv.when == "", iv.when)`：有時間的排前、按字串升冪；`YYYY-MM-DD HH:MM:SS` 字串升冪等同時間升冪。空 `when` 排後。）

同時把 `_snapshot_payload` 開頭「無資料」的早回傳 dict 也加 `"interviews": []`（該分支目前回 viewers/applications/messages 空——加 interviews 空鍵保持形狀一致）：

```python
        return {
            "run_at": None,
            "viewers": [], "applications": [], "messages": [], "interviews": [],
            "digest": "尚無資料，請先重新抓取",
            "failed_readers": failed,
        }
```

- [ ] **Step 4: 跑測試確認通過 + 全測試無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: PASS（全綠）

- [ ] **Step 5: Commit**

```bash
cd sentinel && git add src/career_sentinel/web/app.py tests/test_web_app.py
git commit -m "feat(sentinel): /api/snapshot 輸出 interviews + gcal_link（按時間排序）（SP7）"
```

---

### Task 6: 前端「即將到來的面試」區塊

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（`Interview` 型別 + `SnapshotResp.interviews`）
- Modify: `sentinel/web/frontend/src/Dashboard.tsx`（面試區塊）

**Interfaces:**
- Consumes: `GET /api/snapshot` 的 `interviews`。
- Produces: 儀表板「即將到來的面試」區塊。

- [ ] **Step 1: api.ts 加型別**

在 `sentinel/web/frontend/src/api.ts`：加介面並把 `SnapshotResp` 加 `interviews`：

```typescript
export interface Interview { company: string; job_title: string; when: string; location: string; job_url: string; gcal_link: string }
```

把既有 `SnapshotResp` 介面加一欄位 `interviews: Interview[]`（其餘不動）。

- [ ] **Step 2: Dashboard.tsx 加面試區塊**

在 `sentinel/web/frontend/src/Dashboard.tsx`：
- 從 `./api` 的 import 補上 `type Interview`（若採具名匯入型別）。
- 在「今日彙整」Card **之前**（頂部、面試顯眼）插入面試區塊。用既有 `s`（snapshot data）：

```tsx
      {s && s.interviews.length > 0 && (
        <Card withBorder padding="md" radius="md" mb="md">
          <Title order={4} mb="sm">即將到來的面試（{s.interviews.length}）</Title>
          <Stack gap="xs">
            {s.interviews.map((iv, i) => (
              <Group key={i} justify="space-between" wrap="nowrap">
                <div>
                  <Text fw={600}>{iv.company}　<Text span c="dimmed" size="sm">{iv.job_title}</Text></Text>
                  <Text size="sm" c="dimmed">
                    {iv.when || "日期未擷取"}{iv.location ? ` · ${iv.location}` : ""}
                  </Text>
                </div>
                <Group gap="xs" wrap="nowrap">
                  {iv.job_url && <Anchor href={iv.job_url} target="_blank" size="sm">看職缺</Anchor>}
                  <Button component="a" href={iv.gcal_link} target="_blank" size="xs" variant="light">加入 Google 日曆</Button>
                </Group>
              </Group>
            ))}
          </Stack>
        </Card>
      )}
```

- 確認 `Dashboard.tsx` 頂部的 Mantine import 含 `Anchor`（若無則加入 `Anchor`）。既有已 import `Badge, Button, Card, Container, Group, Stack, Text, Title`——補 `Anchor`。

- [ ] **Step 3: build 確認通過**

Run: `cd sentinel/web/frontend && npm run build`
Expected: build 成功、無 TS 錯誤

- [ ] **Step 4: Commit**

```bash
cd sentinel && git add web/frontend/src/api.ts web/frontend/src/Dashboard.tsx
git commit -m "feat(sentinel): 儀表板即將到來的面試區塊 + 加入 Google 日曆（SP7）"
```

---

### Task 7: 真機驗證 + 收尾

**Files:**
- Modify: `docs/superpowers/career-sentinel-roadmap.md`
- Modify: `.superpowers/sdd/progress.md`

- [ ] **Step 1: 真機端到端驗證**

前提：使用者已 `career-sentinel login`、且帳號有面試邀約紀錄。

```bash
cd sentinel && uv run career-sentinel serve
```
瀏覽器開儀表板 → 按「重新抓取」（headful 爬取，含新的 interviews reader）→ 頂部應出現「即將到來的面試」區塊，列公司/職缺/日期/地點 → 點某筆「加入 Google 日曆」→ 開啟預填好日期與標題的 Google Calendar 新增事件頁。

- [ ] **Step 2: 全測試最終確認**

Run: `cd sentinel && uv run pytest -q`
Expected: PASS（全綠）

- [ ] **Step 3: 更新 roadmap + ledger、commit**

`docs/superpowers/career-sentinel-roadmap.md`：把 SP7 列改為 `| ~~SP7~~ | ~~📅 行事曆整合~~ | ✅ 已完成（見上） | — |`，在「✅ 已完成」區加一條摘要，把 review 期 minors（若有）記入技術債區，並把「`_carry_forward` 寫死三欄位」技術債標為已解（SP7 補了 interviews 第 4 欄位）。
`.superpowers/sdd/progress.md`：append 各 Task 完成與真機驗證結果。

```bash
git add docs/superpowers/career-sentinel-roadmap.md .superpowers/sdd/progress.md
git commit -m "docs(sentinel): SP7 面試擷取+Google 日曆 完成（roadmap + ledger）"
```

---

## Self-Review

**1. Spec coverage：**
- 面試擷取（登入態 `api/interviews`）→ Task 1（`fetch_interviews`）✅
- 解析（含 status 數字保存、raw）→ Task 1（`parse_interviews`）✅
- `Interview` model + `Snapshot.interviews` → Task 1 ✅
- Google 日曆預填連結（有/無時間 fallback、1h 時長、URL-encode）→ Task 2（`build_gcal_link`）✅
- 持久化 interviews → Task 3（store schema/save/load）✅
- 併入既有 scrape reader → Task 4（real.scrape）✅
- `_carry_forward` 第 4 欄位（既有技術債）→ Task 4 ✅
- `/api/snapshot` 輸出 interviews + gcal_link + 按時間排序 → Task 5 ✅
- 儀表板「即將到來的面試」區塊 + 加入日曆 + fallback → Task 6 ✅
- 面試不進 diff/不進通知 → 全程未改 diff/ChangeCounts ✅
- 測試（parse/gcal/store round-trip/scrape/carry_forward/API/build/真機）→ Tasks 1·2·3·4·5·6·7 ✅
- 非目標（Calendar API/面試通知/全分頁）→ 未實作，符合 ✅

**2. Placeholder scan：** 無 TBD/TODO；每個 code step 均含完整程式碼。

**3. Type consistency：**
- `Interview`（company/job_title/when/location/status/job_url/raw）跨 Task 1 定義、Task 2 gcal、Task 3 store、Task 4 scrape、Task 5 payload、Task 6 前端介面一致。
- `Snapshot.interviews` 於 Task 1 加、Task 3 store round-trip、Task 4 carry_forward/scrape、Task 5 payload 一致。
- `build_gcal_link(iv)`（Task 2）與 Task 5 用法一致。
- `parse_interviews`/`fetch_interviews`/`INTERVIEWS_URL`（Task 1）與 Task 4 `real` 用 `fetch_interviews` 一致。
- 前端 `Interview`（company/job_title/when/location/job_url/gcal_link，無 status）與 Task 5 payload 欄位一致。

**開放問題解決紀錄（planning 期實機擷取確認）：** 端點 `pda.104.com.tw/api/interviews`、欄位映射、`interviewTime` 格式 `YYYY-MM-DD HH:MM:SS`、status 數字無 legend（UI 不顯示、存 raw）皆已釘死於 Global Constraints 與 Task 1/2。
