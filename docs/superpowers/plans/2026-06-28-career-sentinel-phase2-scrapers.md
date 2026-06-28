# career-sentinel Phase 2 — 三個真 104 爬蟲 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把假爬蟲換成三個真 104 爬蟲（誰看過我／投遞狀態／訊息），讓 `career-sentinel run` 讀真實登入後資料、存快照、比對變化、LLM 彙整，並加 per-reader 容錯。

**Architecture:** 每類一個檔（`scraper/viewers.py`、`applications.py`、`messages.py`），各自「解析純函式（吃已解 JSON dict、回型別模型，對 `tests/fixtures/*.json` 單測）」與「`fetch_*(page)`（`page.request.get` 取數，需真瀏覽器、不單測）」分離。`scraper/real.py` 編排三讀取器（逐個 try/except → `(Snapshot, failed_readers)`）。`cli.run_pipeline` 對失敗類沿用上次快照避免污染；`_cmd_run` 改在 playwright context 內呼叫 `real.scrape(page)`。

**Tech Stack:** Python 3.12+、rebrowser-playwright（headful）、Pydantic v2、pytest。

## Global Constraints

- `sentinel/` 獨立，**不 import/依賴** `backend/`、`frontend/`；套件名 `career_sentinel`。
- 取數用已登入 context 的 `page.request.get(<api>)`；**pda.104.com.tw 的 API 需先 navigate 一個 pda 頁取得該 host 的 Cloudflare clearance**（cf_clearance 綁 host）。
- **headless 過不了 Cloudflare，一律 headful**（`open_context` 已是）。
- 抓取/解析分離：`parse_*`/`derive_status`/`has_interview` 是純函式、對 `tests/fixtures/*.json` 單測；`fetch_*`/`establish_session` 需真瀏覽器、不單測（由 Task 6 真機 run 驗證）。
- 不改 Phase 1 既有行為（models/store/diff/digest 不動；只擴充 `run_pipeline` 與假爬蟲簽章）。
- MVP：每類只第 1 頁；面試只標記有無（`invite_date=None`）；訊息抓 `exclusive`+`general` 兩 filter。
- 驗證閘門：`cd sentinel && uv run pytest` 全綠。
- fixtures 已存在：`sentinel/tests/fixtures/{viewers,messages,applications}.json`（去識別化，結構同真實）。

---

### Task 1: viewers 爬蟲（誰看過我）

**Files:**
- Create: `sentinel/src/career_sentinel/scraper/viewers.py`
- Test: `sentinel/tests/test_parse_viewers.py`

**Interfaces:**
- Consumes：`models.Viewer`；`tests/fixtures/viewers.json`。
- Produces：
  - `VIEWERS_URL: str`
  - `parse_viewers(data: dict) -> list[Viewer]`（純函式）
  - `fetch_viewers(page) -> list[Viewer]`（`page.request.get` + parse；不單測）

- [ ] **Step 1: 寫失敗測試 `tests/test_parse_viewers.py`**

```python
import json
from pathlib import Path

from career_sentinel.scraper.viewers import parse_viewers

FIX = Path(__file__).parent / "fixtures" / "viewers.json"


def test_parse_viewers_maps_fields():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    viewers = parse_viewers(data)
    assert len(viewers) == 2
    v = viewers[0]
    assert v.company == "範例科技股份有限公司"
    assert v.job_title == "軟體工程師"        # jobCatTag.desc
    assert v.viewed_at == "2026-06-28 09:12"  # browseDate
    assert v.raw["custNo"] == "1a2b3c"


def test_parse_viewers_empty():
    assert parse_viewers({"data": []}) == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_parse_viewers.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `scraper/viewers.py`**

```python
from __future__ import annotations

from ..models import Viewer

VIEWERS_URL = "https://pda.104.com.tw/api/peruse-record/companies?page=1"


def parse_viewers(data: dict) -> list[Viewer]:
    out: list[Viewer] = []
    for item in data.get("data", []):
        out.append(
            Viewer(
                company=item.get("custName", ""),
                job_title=(item.get("jobCatTag") or {}).get("desc", ""),
                viewed_at=item.get("browseDate", ""),
                raw=item,
            )
        )
    return out


def fetch_viewers(page) -> list[Viewer]:
    """需已登入且已取得 pda host 的 Cloudflare clearance。需真瀏覽器、不單測。"""
    resp = page.request.get(VIEWERS_URL)
    return parse_viewers(resp.json())
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_parse_viewers.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/scraper/viewers.py sentinel/tests/test_parse_viewers.py
git commit -m "feat(sentinel): viewers 爬蟲（誰看過我 parse + fetch）"
```

---

### Task 2: applications 爬蟲（投遞狀態 + derive_status）

**Files:**
- Create: `sentinel/src/career_sentinel/scraper/applications.py`
- Test: `sentinel/tests/test_parse_applications.py`

**Interfaces:**
- Consumes：`models.Application`；`tests/fixtures/applications.json`。
- Produces：
  - `APPLICATIONS_URL: str`
  - `derive_status(item: dict) -> str`（純函式）
  - `parse_applications(data: dict) -> list[Application]`（純函式）
  - `fetch_applications(page) -> list[Application]`（不單測）

- [ ] **Step 1: 寫失敗測試 `tests/test_parse_applications.py`**

```python
import json
from pathlib import Path

from career_sentinel.scraper.applications import derive_status, parse_applications

FIX = Path(__file__).parent / "fixtures" / "applications.json"


def test_derive_status_sent():
    assert derive_status({"custCheckDate": "", "custReplyDate": "", "hrReplyCount": 0}) == "已送出"


def test_derive_status_read():
    assert derive_status({"custCheckDate": "2026/06/28 20:00:00", "custReplyDate": "", "hrReplyCount": 0}) == "已讀"


def test_derive_status_replied_by_date():
    assert derive_status({"custCheckDate": "x", "custReplyDate": "2026/06/29", "hrReplyCount": 0}) == "公司已回覆"


def test_derive_status_replied_by_count():
    assert derive_status({"custCheckDate": "x", "custReplyDate": "", "hrReplyCount": 2}) == "公司已回覆"


def test_parse_applications_maps_fields():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    apps = parse_applications(data)
    assert len(apps) == 1
    a = apps[0]
    assert a.job_id == "99999999"           # str(jobNo)
    assert a.company == "範例電腦股份有限公司"
    assert a.title == "範例軟體開發工程師"
    assert a.applied_at == "2026/06/28 19:10:26"
    assert a.status == "已讀"                # custCheckDate 有值、未回覆
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_parse_applications.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `scraper/applications.py`**

```python
from __future__ import annotations

from ..models import Application

APPLICATIONS_URL = "https://pda.104.com.tw/applyRecord/ajax/list?page=1&status=all"


def derive_status(item: dict) -> str:
    """104 無單一狀態欄位，由時間戳推導。"""
    if item.get("custReplyDate") or (item.get("hrReplyCount") or 0) > 0:
        return "公司已回覆"
    if item.get("custCheckDate"):
        return "已讀"
    return "已送出"


def parse_applications(data: dict) -> list[Application]:
    out: list[Application] = []
    for item in data.get("data", []):
        out.append(
            Application(
                job_id=str(item.get("jobNo", "")),
                company=item.get("custName", ""),
                title=item.get("jobName", ""),
                status=derive_status(item),
                applied_at=item.get("applyDate", ""),
                raw=item,
            )
        )
    return out


def fetch_applications(page) -> list[Application]:
    """需已登入且已取得 pda host clearance。需真瀏覽器、不單測。"""
    resp = page.request.get(APPLICATIONS_URL)
    return parse_applications(resp.json())
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_parse_applications.py -v`
Expected: PASS（5 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/scraper/applications.py sentinel/tests/test_parse_applications.py
git commit -m "feat(sentinel): applications 爬蟲（投遞狀態 parse + derive_status）"
```

---

### Task 3: messages 爬蟲（訊息/面試 + has_interview）

**Files:**
- Create: `sentinel/src/career_sentinel/scraper/messages.py`
- Test: `sentinel/tests/test_parse_messages.py`

**Interfaces:**
- Consumes：`models.Message`；`tests/fixtures/messages.json`。
- Produces：
  - `MESSAGES_URLS: list[str]`（exclusive + general）
  - `has_interview(item: dict) -> bool`（純函式）
  - `parse_messages(data: dict) -> list[Message]`（純函式）
  - `fetch_messages(page) -> list[Message]`（兩 filter 合併；不單測）

- [ ] **Step 1: 寫失敗測試 `tests/test_parse_messages.py`**

```python
import json
from pathlib import Path

from career_sentinel.scraper.messages import has_interview, parse_messages

FIX = Path(__file__).parent / "fixtures" / "messages.json"


def test_has_interview_by_event_desc():
    assert has_interview({"lastEvent": {"desc": "面試邀約"}, "msg": "您好"}) is True


def test_has_interview_by_msg():
    assert has_interview({"lastEvent": {"desc": "已回覆"}, "msg": "想約您面試"}) is True


def test_has_interview_false():
    assert has_interview({"lastEvent": {"desc": "已回覆"}, "msg": "感謝您的應徵"}) is False


def test_parse_messages_maps_fields():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    msgs = parse_messages(data)
    assert len(msgs) == 2
    m = msgs[0]
    assert m.thread_id == "room-aaa"
    assert m.company == "範例科技股份有限公司"
    assert m.last_message == "想邀請您本週四下午來面試"
    assert m.has_interview_invite is True
    assert m.invite_date is None
    assert msgs[1].has_interview_invite is False
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_parse_messages.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `scraper/messages.py`**

```python
from __future__ import annotations

from ..models import Message

MESSAGES_URLS = [
    "https://pda.104.com.tw/api/messages/chatrooms?filter=exclusive&page=1&pageSize=20",
    "https://pda.104.com.tw/api/messages/chatrooms?filter=general&page=1&pageSize=20",
]


def has_interview(item: dict) -> bool:
    desc = (item.get("lastEvent") or {}).get("desc", "") or ""
    msg = item.get("msg", "") or ""
    return "面試" in desc or "面試" in msg


def parse_messages(data: dict) -> list[Message]:
    out: list[Message] = []
    for item in data.get("data", []):
        out.append(
            Message(
                thread_id=str(item.get("chatroomId", "")),
                company=item.get("custName", ""),
                last_message=item.get("msg", "") or "",
                has_interview_invite=has_interview(item),
                invite_date=None,
                raw=item,
            )
        )
    return out


def fetch_messages(page) -> list[Message]:
    """抓 exclusive + general 兩 filter 合併。需真瀏覽器、不單測。"""
    out: list[Message] = []
    for url in MESSAGES_URLS:
        resp = page.request.get(url)
        out.extend(parse_messages(resp.json()))
    return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_parse_messages.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/scraper/messages.py sentinel/tests/test_parse_messages.py
git commit -m "feat(sentinel): messages 爬蟲（訊息 parse + 面試啟發式）"
```

---

### Task 4: real.py 編排器（establish_session + scrape + 容錯）

**Files:**
- Create: `sentinel/src/career_sentinel/scraper/real.py`
- Test: `sentinel/tests/test_real_scrape.py`

**Interfaces:**
- Consumes：`browser.{wait_until_ready,is_login_url}`、`models.Snapshot`、`viewers.fetch_viewers`、`applications.fetch_applications`、`messages.fetch_messages`。
- Produces：
  - `ESTABLISH_URL: str`
  - `establish_session(page) -> bool`（navigate pda + 確認登入；需真瀏覽器、不單測）
  - `scrape(page) -> tuple[Snapshot, set[str]]`（逐讀取器 try/except）

**測試策略：** `scrape` 在函式內以名稱引用 `fetch_viewers`/`fetch_applications`/`fetch_messages`（real 模組全域），故可 `monkeypatch.setattr(real, "fetch_viewers", ...)` 測編排與容錯，毋需真瀏覽器。

- [ ] **Step 1: 寫失敗測試 `tests/test_real_scrape.py`**

```python
from career_sentinel.scraper import real
from career_sentinel.models import Application, Message, Viewer


def test_scrape_collects_all(monkeypatch):
    monkeypatch.setattr(real, "fetch_viewers", lambda page: [Viewer(company="A", job_title="x", viewed_at="t")])
    monkeypatch.setattr(real, "fetch_applications", lambda page: [Application(job_id="1", company="A", title="x", status="已讀", applied_at="t")])
    monkeypatch.setattr(real, "fetch_messages", lambda page: [Message(thread_id="t1", company="A", last_message="hi")])
    snap, failed = real.scrape(object())
    assert failed == set()
    assert len(snap.viewers) == 1
    assert len(snap.applications) == 1
    assert len(snap.messages) == 1


def test_scrape_isolates_one_failure(monkeypatch):
    def boom(page):
        raise RuntimeError("down")

    monkeypatch.setattr(real, "fetch_viewers", boom)
    monkeypatch.setattr(real, "fetch_applications", lambda page: [Application(job_id="1", company="A", title="x", status="已讀", applied_at="t")])
    monkeypatch.setattr(real, "fetch_messages", lambda page: [])
    snap, failed = real.scrape(object())
    assert failed == {"viewers"}
    assert snap.viewers == []
    assert len(snap.applications) == 1
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_real_scrape.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `scraper/real.py`**

```python
from __future__ import annotations

from .. import browser
from ..models import Snapshot
from .applications import fetch_applications
from .messages import fetch_messages
from .viewers import fetch_viewers

ESTABLISH_URL = "https://pda.104.com.tw/"


def establish_session(page) -> bool:
    """navigate 一個 pda 頁（取得該 host 的 Cloudflare clearance）並確認已登入。

    需真瀏覽器、不單測。回 False 代表未登入（呼叫端應提示先 login）。
    """
    page.goto(ESTABLISH_URL, wait_until="domcontentloaded")
    browser.wait_until_ready(page)
    return not browser.is_login_url(page.url)


def scrape(page) -> tuple[Snapshot, set[str]]:
    """逐讀取器抓取；單一失敗只記進 failed、不中斷其他。"""
    readers = (
        ("viewers", fetch_viewers),
        ("applications", fetch_applications),
        ("messages", fetch_messages),
    )
    collected: dict[str, list] = {"viewers": [], "applications": [], "messages": []}
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
    )
    return snapshot, failed
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_real_scrape.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/scraper/real.py sentinel/tests/test_real_scrape.py
git commit -m "feat(sentinel): real.scrape 編排三讀取器 + per-reader 容錯"
```

---

### Task 5: 假爬蟲回 tuple + run_pipeline 容錯沿用

**Files:**
- Modify: `sentinel/src/career_sentinel/scraper/fake.py`
- Modify: `sentinel/src/career_sentinel/cli.py`（`run_pipeline` + 新增 `_carry_forward`）
- Modify: `sentinel/tests/test_fake_scraper.py`
- Modify: `sentinel/tests/test_cli.py`

**Interfaces:**
- Consumes：`store.{latest_two_ids,load_snapshot,save_snapshot,connect}`、`diff.diff_against_last`、`digest.summarize`、`models.Snapshot`。
- Produces：
  - `fake.scrape() -> tuple[Snapshot, set[str]]`（回空 failed set）
  - `run_pipeline(scrape, conn, *, now) -> str`（吃回 `(Snapshot, set)` 的 scrape；失敗類沿用上次快照、報告附警告）

- [ ] **Step 1: 改 `tests/test_fake_scraper.py`（解包 tuple）**

把 `tests/test_fake_scraper.py` 全檔換成：

```python
from career_sentinel.scraper import fake
from career_sentinel.models import Snapshot


def test_fake_scrape_returns_populated_snapshot_and_empty_failed():
    snap, failed = fake.scrape()
    assert isinstance(snap, Snapshot)
    assert failed == set()
    assert snap.viewers and snap.applications and snap.messages
    assert any(m.has_interview_invite for m in snap.messages)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_fake_scraper.py -v`
Expected: FAIL（目前 `fake.scrape()` 回 `Snapshot`，解包成 `snap, failed` 會 `ValueError: too many values to unpack` 或 `TypeError`）。

- [ ] **Step 3: 改 `scraper/fake.py` 回 tuple**

把 `fake.py` 的 `scrape` 簽章與 return 改為（資料內容不變，僅尾端加 `set()`）：

```python
def scrape() -> tuple[Snapshot, set[str]]:
    """本階段假資料；真爬蟲在 scraper/real.py。回 (Snapshot, 空 failed set)。"""
    snapshot = Snapshot(
        viewers=[
            Viewer(company="台積電", job_title="資深後端工程師", viewed_at="2026-06-28 09:12"),
            Viewer(company="聯發科", job_title="平台軟體工程師", viewed_at="2026-06-27 18:40"),
        ],
        applications=[
            Application(job_id="j-1001", company="台積電", title="資深後端工程師", status="邀請面試", applied_at="2026-06-20"),
            Application(job_id="j-1002", company="某新創", title="全端工程師", status="不適合", applied_at="2026-06-18"),
        ],
        messages=[
            Message(thread_id="th-1", company="台積電", last_message="想邀請您本週四面試", has_interview_invite=True, invite_date="2026-07-03"),
            Message(thread_id="th-2", company="某新創", last_message="感謝您的應徵", has_interview_invite=False),
        ],
    )
    return snapshot, set()
```

（檔案頂端的 `from ..models import Application, Message, Snapshot, Viewer` 不變。）

- [ ] **Step 4: 跑 fake 測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_fake_scraper.py -v`
Expected: PASS（1 passed）。

- [ ] **Step 5: 在 `tests/test_cli.py` 加容錯沿用測試**

在 `tests/test_cli.py` 頂端的 import 區加入（若尚未有）：

```python
from career_sentinel.models import Snapshot
```

並在檔案末加入新測試：

```python
def test_run_pipeline_carries_forward_failed_reader(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    cli.run_pipeline(fake.scrape, conn, now="2026-06-28T10:00:00")

    def scrape_viewers_failed():
        snap, _ = fake.scrape()
        return Snapshot(viewers=[], applications=snap.applications, messages=snap.messages), {"viewers"}

    report = cli.run_pipeline(scrape_viewers_failed, conn, now="2026-06-29T10:00:00")
    assert "未讀到" in report and "viewers" in report
    ids = store.latest_two_ids(conn)
    latest = store.load_snapshot(conn, ids[0])
    assert len(latest.viewers) == 2  # 沿用上次的兩筆、未被空清單污染
```

- [ ] **Step 6: 跑 cli 測試確認新測試失敗**

Run: `cd sentinel && uv run pytest tests/test_cli.py -v`
Expected: 既有 3 測試仍因 `run_pipeline` 尚未支援 tuple 而 FAIL（`fake.scrape()` 現回 tuple，舊 `run_pipeline` 把 tuple 當 Snapshot 存會壞），新測試亦 FAIL。先確認紅燈。

- [ ] **Step 7: 改 `cli.py` 的 `run_pipeline` 支援 (Snapshot, failed) + 沿用**

把 `cli.py` 內現有的 `run_pipeline` 函式整段替換為：

```python
def run_pipeline(scrape: Callable[[], tuple[Snapshot, set[str]]], conn, *, now: str) -> str:
    snapshot, failed = scrape()
    if failed:
        snapshot = _carry_forward(conn, snapshot, failed)
    sid = store.save_snapshot(conn, snapshot, run_at=now)
    d = diff.diff_against_last(conn, sid)
    report = digest.summarize(d, snapshot)
    if failed:
        report += "\n\n⚠️ 本次未讀到：" + "、".join(sorted(failed)) + "（沿用上次）"
    return report


def _carry_forward(conn, snapshot: Snapshot, failed: set[str]) -> Snapshot:
    """失敗的讀取器沿用上次快照同類資料，避免下次 diff 把整類誤判為新。"""
    ids = store.latest_two_ids(conn)
    if not ids:
        return snapshot
    prev = store.load_snapshot(conn, ids[0])
    return Snapshot(
        viewers=prev.viewers if "viewers" in failed else snapshot.viewers,
        applications=prev.applications if "applications" in failed else snapshot.applications,
        messages=prev.messages if "messages" in failed else snapshot.messages,
    )
```

（`Callable` 已在 `cli.py` 頂端 `from typing import Callable` 匯入；`Snapshot` 已 `from .models import Snapshot` 匯入——皆 Phase 1 既有，不需新增。）

- [ ] **Step 8: 跑全測試確認通過**

Run: `cd sentinel && uv run pytest -v`
Expected: 全 PASS（含 test_cli 既有 3 + 新增 1 + 其餘全部）。既有「第二次相同 run 回『沒有新變化』」仍成立（`failed` 為空、不沿用）。

- [ ] **Step 9: Commit**

```bash
git add sentinel/src/career_sentinel/scraper/fake.py sentinel/src/career_sentinel/cli.py sentinel/tests/test_fake_scraper.py sentinel/tests/test_cli.py
git commit -m "feat(sentinel): 假爬蟲回 (Snapshot,failed) + run_pipeline 失敗類沿用上次快照"
```

---

### Task 6: `_cmd_run` 接真爬蟲 + 真機驗證

**Files:**
- Modify: `sentinel/src/career_sentinel/cli.py`（`_cmd_run`）

**Interfaces:**
- Consumes：`scraper.real.{establish_session,scrape}`、`run_pipeline`、`browser.open_context`、`store`、`config`。
- Produces：無新對外符號。

**註：** `_cmd_run` 需真瀏覽器、不單測；以全測試不回歸 + 一次真機 `run` 驗證。

- [ ] **Step 1: 改 `cli.py` 的 `_cmd_run`**

把 `cli.py` 內現有的 `_cmd_run` 函式整段替換為（pipeline 呼叫移進 context、改用 `real.scrape`；`establish_session` 兼作登入檢查）：

```python
def _cmd_run() -> int:
    from rebrowser_playwright.sync_api import sync_playwright

    from .scraper import real

    conn = store.connect(config.db_path())
    with sync_playwright() as p:
        ctx = browser.open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if not real.establish_session(page):
            ctx.close()
            print("尚未登入，請先執行：career-sentinel login")
            return 1
        report = run_pipeline(
            lambda: real.scrape(page),
            conn,
            now=datetime.now().isoformat(timespec="seconds"),
        )
        ctx.close()
    print(report)
    return 0
```

（`fake` 的頂端 import 可保留不動——`run_pipeline`/測試仍用得到。`datetime`、`browser`、`store`、`config`、`run_pipeline` 皆 Phase 1 既有匯入。）

- [ ] **Step 2: 跑全測試確認無回歸**

Run: `cd sentinel && uv run pytest -v`
Expected: 全 PASS（`_cmd_run` 不被單測涵蓋，但不得弄壞既有測試）。

- [ ] **Step 3: 真機驗證 `run`（需已 `login` 過、profile 有登入態、且登入視窗已關）**

Run: `cd sentinel && uv run career-sentinel run`
Expected（任一即算通過，重點是不崩潰、有輸出）：
- 印出今日彙整（首次＝三類目前內容；之後＝跟上次比的變化）；或
- 某類端點被擋時印出「⚠️ 本次未讀到：<類>（沿用上次）」其餘正常；或
- 未登入時印「尚未登入，請先執行：career-sentinel login」。

若三類都被 Cloudflare 擋（`page.request.get` 拿不到 JSON）→ 採 spec 開放問題的退路：改成「navigate 各自頁面 + 攔截回應」。此情況回報控制器調整 `fetch_*`（本步驟記錄結果即可，不在此擴充計畫）。

- [ ] **Step 4: Commit**

```bash
git add sentinel/src/career_sentinel/cli.py
git commit -m "feat(sentinel): run 接真爬蟲 scraper.real（establish_session + scrape，修 ctx 順序）"
```

---

## 完成後

`career-sentinel run` 讀真實 104 三類資料、存快照、比對變化、LLM 彙整、容錯沿用。
後續子專案（各自 spec→plan）：全分頁、面試確切日期 + 行事曆整合、每日自動排程、對話式履歷整理、公司評價 web 研究。
