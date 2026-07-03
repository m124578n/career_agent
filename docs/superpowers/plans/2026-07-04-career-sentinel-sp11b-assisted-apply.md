# career-sentinel SP11b 半自動投遞（開頁＋帶文案）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 客製化分頁「開啟投遞頁」按鈕：用登入態純 Chrome 開該職缺頁供使用者親手應徵（agent 不寫入 104、不填表、不 POST）。

**Architecture:** `web/apply.py`（`open_job_page`：find_chrome + subprocess.Popen 開網址，同 login 機制）→ `POST /api/apply/open`（`try_begin_browser` 守 launch 瞬間、錯誤對映）→ TailorPage 加按鈕。追蹤沿用既有「我的應徵」，不新增爬蟲/資料表。

**Tech Stack:** Python 3.12、FastAPI、subprocess、既有 `browser.find_chrome`/`config.profile_dir`/`runner.try_begin_browser`、React 18 + Mantine 7。

**Spec:** `docs/superpowers/specs/2026-07-04-career-sentinel-sp11b-assisted-apply-design.md`

## Global Constraints

- **agent 全程不寫入 104**：只 `subprocess.Popen` 開一個網址（同 `cli._cmd_login`），不 POST、不填表、不碰投遞 API、不新增爬蟲/資料表。
- 端點錯誤對映：無 job_url→400「請提供職缺網址」、瀏覽器忙碌（`try_begin_browser` 回 False）→409「瀏覽器忙碌中（可能正在抓取），請稍候再試」、找不到 Chrome（`find_chrome` 回 None）→500「找不到 Google Chrome，請確認已安裝」、成功→`{"status": "opened"}`。
- **旗標配對鐵律**：`try_begin_browser` 回 True 後**任何**返回路徑（含 no-chrome 500）都必須 `end_browser`；忙碌（未 begin）路徑**不得** `end_browser`。
- Popen 參數同 login：`[chrome, f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", job_url]`；profile＝`config.profile_dir()`。
- 測試全 monkeypatch（`find_chrome`/`Popen`/`try_begin_browser`/`end_browser`），**不真的開 Chrome、不真的碰 104**；輸出 pristine（僅既有 Starlette warning）。
- 前端：投遞按鈕 tangerine 主動作；網路呼叫 try/finally；409/500 頁內 danger 顯示；Tabler icon 無 emoji；`npm run build` 零 TS 錯誤。
- 追蹤沿用既有 applications 爬蟲＋儀表板「我的應徵」，不做投遞紀錄表。
- 分支 `dev`；commit `feat(sentinel): ...（SP11b）`＋trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。

---

## File Structure

- Create: `sentinel/src/career_sentinel/web/apply.py`（`open_job_page`）
- Modify: `sentinel/src/career_sentinel/web/app.py`（`POST /api/apply/open`）
- Modify: `sentinel/web/frontend/src/api.ts`、`sentinel/web/frontend/src/TailorPage.tsx`
- Test: `sentinel/tests/test_apply.py`（新）、`sentinel/tests/test_web_app.py`（追加）

後端指令在 `sentinel/` 下執行。

---

### Task 1: `web/apply.py` + `POST /api/apply/open` 端點

**Files:**
- Create: `sentinel/src/career_sentinel/web/apply.py`
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_apply.py`（新檔）、`sentinel/tests/test_web_app.py`（檔尾追加）

**Interfaces:**
- Consumes: `browser.find_chrome() -> str | None`、`config.profile_dir() -> Path`、`runner.try_begin_browser() -> bool`、`runner.end_browser() -> None`。
- Produces: `apply.open_job_page(job_url: str) -> bool`（找到 Chrome 並 Popen 回 True；找不到 Chrome 回 False）；`POST /api/apply/open`。

- [ ] **Step 1: 寫 apply.py 失敗測試**（`sentinel/tests/test_apply.py` 新檔）

```python
from career_sentinel.web import apply


def test_open_job_page_launches_chrome(monkeypatch):
    calls = {}
    monkeypatch.setattr(apply.browser, "find_chrome", lambda: "/usr/bin/chrome")
    monkeypatch.setattr(apply.config, "profile_dir", lambda: apply.Path("/tmp/prof"))
    monkeypatch.setattr(apply.subprocess, "Popen", lambda args, **kw: calls.setdefault("args", args))
    assert apply.open_job_page("https://www.104.com.tw/job/abc") is True
    args = calls["args"]
    assert args[0] == "/usr/bin/chrome"
    assert "--user-data-dir=/tmp/prof" in args or f"--user-data-dir={apply.Path('/tmp/prof')}" in args
    assert args[-1] == "https://www.104.com.tw/job/abc"


def test_open_job_page_no_chrome(monkeypatch):
    monkeypatch.setattr(apply.browser, "find_chrome", lambda: None)
    popen_called = {"n": 0}
    monkeypatch.setattr(apply.subprocess, "Popen", lambda *a, **k: popen_called.__setitem__("n", 1))
    assert apply.open_job_page("u") is False
    assert popen_called["n"] == 0  # 沒 Chrome 不啟動
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_apply.py -q`
Expected: FAIL（ModuleNotFoundError: career_sentinel.web.apply）

- [ ] **Step 3: 實作 apply.py**（`sentinel/src/career_sentinel/web/apply.py` 新檔）

```python
"""SP11b 半自動投遞：用登入態純 Chrome 開職缺頁供使用者親手應徵。

不 POST、不填表、不碰 104 投遞 API——只 subprocess 開一個網址（同 cli login 機制）。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .. import browser, config


def open_job_page(job_url: str) -> bool:
    """用專案 profile（登入態）的純 Chrome 開職缺頁。找不到 Chrome 回 False。"""
    chrome = browser.find_chrome()
    if not chrome:
        return False
    profile = config.profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            chrome,
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            job_url,
        ]
    )
    return True
```

- [ ] **Step 4: 跑 apply.py 測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_apply.py -q`
Expected: 2 passed

- [ ] **Step 5: 寫端點失敗測試**（`sentinel/tests/test_web_app.py` 檔尾追加）

```python
def test_apply_open_success(tmp_path, monkeypatch):
    from career_sentinel.web import apply, runner
    flags = {"begin": 0, "end": 0}
    monkeypatch.setattr(runner, "try_begin_browser", lambda: flags.__setitem__("begin", flags["begin"] + 1) or True)
    monkeypatch.setattr(runner, "end_browser", lambda: flags.__setitem__("end", flags["end"] + 1))
    monkeypatch.setattr(apply, "open_job_page", lambda url: True)
    r = _client(tmp_path).post("/api/apply/open", json={"job_url": "https://www.104.com.tw/job/abc"})
    assert r.status_code == 200 and r.json() == {"status": "opened"}
    assert flags["begin"] == 1 and flags["end"] == 1  # 成對


def test_apply_open_empty_url(tmp_path):
    assert _client(tmp_path).post("/api/apply/open", json={"job_url": ""}).status_code == 400


def test_apply_open_browser_busy(tmp_path, monkeypatch):
    from career_sentinel.web import runner
    flags = {"end": 0}
    monkeypatch.setattr(runner, "try_begin_browser", lambda: False)
    monkeypatch.setattr(runner, "end_browser", lambda: flags.__setitem__("end", 1))
    r = _client(tmp_path).post("/api/apply/open", json={"job_url": "u"})
    assert r.status_code == 409
    assert flags["end"] == 0  # 未 begin 不該 end


def test_apply_open_no_chrome(tmp_path, monkeypatch):
    from career_sentinel.web import apply, runner
    flags = {"end": 0}
    monkeypatch.setattr(runner, "try_begin_browser", lambda: True)
    monkeypatch.setattr(runner, "end_browser", lambda: flags.__setitem__("end", 1))
    monkeypatch.setattr(apply, "open_job_page", lambda url: False)
    r = _client(tmp_path).post("/api/apply/open", json={"job_url": "u"})
    assert r.status_code == 500
    assert flags["end"] == 1  # begin 成功後即使 no-chrome 也要 end
```

- [ ] **Step 6: 跑端點測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_app.py -q -k apply_open`
Expected: FAIL（404）

- [ ] **Step 7: 實作端點**（`sentinel/src/career_sentinel/web/app.py`）

import 區（`from . import runner, scheduler` 那行）改為：

```python
from . import apply, runner, scheduler
```

`tailor_job` 端點（`@app.post("/api/tailor")`…`return result.model_dump()`）**之後**追加：

```python
    @app.post("/api/apply/open")
    def apply_open(req: _MatchReq) -> dict:
        if not req.job_url.strip():
            raise HTTPException(status_code=400, detail="請提供職缺網址")
        if not runner.try_begin_browser():
            raise HTTPException(status_code=409, detail="瀏覽器忙碌中（可能正在抓取），請稍候再試")
        try:
            ok = apply.open_job_page(req.job_url.strip())
        finally:
            runner.end_browser()
        if not ok:
            raise HTTPException(status_code=500, detail="找不到 Google Chrome，請確認已安裝")
        return {"status": "opened"}
```

- [ ] **Step 8: 全套測試**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠（225＋新 6）

- [ ] **Step 9: Commit**

```bash
git add sentinel/src/career_sentinel/web/apply.py sentinel/src/career_sentinel/web/app.py sentinel/tests/test_apply.py sentinel/tests/test_web_app.py
git commit -m "feat(sentinel): POST /api/apply/open——登入態 Chrome 開職缺頁（agent 不寫入）（SP11b）"
```

---

### Task 2: 前端「開啟投遞頁」按鈕

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（檔尾追加）
- Modify: `sentinel/web/frontend/src/TailorPage.tsx`

**Interfaces:**
- Consumes: Task 1 端點；TailorPage 既有 `url` state（客製化用的職缺網址）。
- Produces: 客製化結果下方「開啟投遞頁」按鈕。

- [ ] **Step 1: api.ts 追加**

```ts
export async function openApplyPage(job_url: string): Promise<Response> {
  return fetch("/api/apply/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_url }),
  });
}
```

- [ ] **Step 2: TailorPage.tsx 加按鈕與狀態**

檔頭：
- api import 加入 `openApplyPage`（併入既有 `{ getResume, tailorApplication, type TailoredApplication }`）。
- tabler import 加 `IconExternalLink`。

元件內、既有 `const [copied, setCopied] = useState(false);` 之後加：

```tsx
  const [applyBusy, setApplyBusy] = useState(false);
  const [applyErr, setApplyErr] = useState<string | null>(null);

  async function openApply() {
    setApplyErr(null);
    setApplyBusy(true);
    try {
      const r = await openApplyPage(url.trim());
      if (!r.ok) {
        const b = await r.json().catch(() => ({}));
        setApplyErr(b.detail ?? "開啟失敗");
      }
    } catch {
      setApplyErr("網路錯誤，請重試");
    } finally {
      setApplyBusy(false);
    }
  }
```

求職信 Paper（`{data && (...)}` 內、`</Stack>` 結束之前——即求職信 Paper 之後）加投遞區塊：

```tsx
          <Paper bg="dark.6" radius="md" p="lg">
            <Text size="sm" c="dimmed" mb="sm">
              將用你的登入態 Chrome 開啟該職缺頁，請在瀏覽器中親手應徵、貼上求職信並送出。
            </Text>
            <Button
              leftSection={<IconExternalLink size={16} />}
              onClick={openApply}
              loading={applyBusy}
            >
              開啟投遞頁
            </Button>
            {applyErr && <Text c="danger.6" size="sm" mt="sm">{applyErr}</Text>}
          </Paper>
```

- [ ] **Step 3: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 零 TS 錯誤

- [ ] **Step 4: Commit**

```bash
git add src/api.ts src/TailorPage.tsx
git commit -m "feat(sentinel): 客製化分頁「開啟投遞頁」按鈕（SP11b）"
```

---

### Task 3: 真機驗證 + 收尾

**Files:**
- Modify: `docs/superpowers/career-sentinel-roadmap.md`

- [ ] **Step 1: 真機驗證（需使用者操作）**

serve 重啟 → Ctrl+F5 → 客製化分頁：
1. 貼一個想投遞的職缺網址 → 客製化 → 複製求職信
2. 點「開啟投遞頁」→ 登入態純 Chrome 開該職缺頁（已登入、過 Cloudflare）、看得到「應徵」按鈕
3. 在 Chrome 中親手應徵、貼上求職信、送出
4. 忙碌情境：抓取進行中點投遞 → 顯示 409 忙碌提示
5. （投遞後）下次「重新抓取」→ 該職缺出現在儀表板「我的應徵」

- [ ] **Step 2: roadmap 收尾 + Commit**

SP11b 表格列劃掉、✅ 區加摘要（含「agent 不寫入、無需逆向投遞端點」的模型說明）、review minors 記技術債區、更新日期。

```bash
git add docs/superpowers/career-sentinel-roadmap.md
git commit -m "docs(sentinel): SP11b 半自動投遞完成（roadmap 收尾）"
```
