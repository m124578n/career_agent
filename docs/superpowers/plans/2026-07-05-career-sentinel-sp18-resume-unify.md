# SP18：履歷合一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `履歷健檢`（上傳 PDF/TXT）與 `104 履歷`（讀線上）兩個入口合成一個「我的履歷」頁，單一作用中 `resume_text`，來源可為上傳檔案或從 104 匯入（去 PII 攤平）。

**Architecture:** `ResumeState` 加 `source` 欄（加法式相容）；新 `POST /api/resume/import104` 讀 104→`flatten_for_diagnosis` 去 PII→設為作用中 resume_text；移除已被取代的 `/api/resume104/diagnose` 與 `GET /api/resume104`。前端新 `ProfilePage`（來源切換：上傳／104 匯入，含 104 區塊檢視＋開編輯頁）取代 ResumePage＋Resume104Page，導覽兩項收一項。

**Tech Stack:** Python 3.12、Pydantic v2、FastAPI、SQLite、pytest；React 18 ＋ Vite ＋ Mantine 7（SegmentedControl）＋ TanStack Query。

## Global Constraints

- **PII 不外流**：104 履歷 PII 區塊（`is_pii=True`）只在瀏覽器本地顯示；`resume_text`（進 DB、送 LLM）一律為 `flatten_for_diagnosis` 去 PII 後的文字。import104 絕不把 PII 寫入 `resume_text`。
- **讀 104 需登入態瀏覽器**：`import104` 用 `runner.try_begin_browser()/end_browser()` 圍住 `resume104_session()`；未登入回 409（文案「尚未登入，請先在終端機執行：career-sentinel login」）；瀏覽器忙碌回 409；不寫入 104。
- **單一作用中履歷**：上傳或 104 匯入都覆寫同一份 `resume_text` 並設 `source`；比對/客製化/健檢統一用這份（既有端點讀 `state.resume_text` 行為不變）。
- **相容**：`ResumeState` 加 `source` 為加法式（舊 JSON 無此欄→`""`），不需遷移；`/api/resume/upload`、`/api/resume/diagnose`、`/api/match`、`/api/tailor` 回傳/行為不變（只多存/回 source）。
- 目標職稱／期望薪資 SP18 仍留在「我的履歷」頁（SP19 才搬進偏好區）。
- 後端綁 `127.0.0.1`；前端 `npm run build`（noUnusedLocals）必過。
- 測試：後端 `cd sentinel && ./.venv/Scripts/python.exe -m pytest`；前端 `cd sentinel/web/frontend && npm run build`。

---

### Task 1: 後端 — ResumeState.source ＋ import104 ＋ 移除舊 104 端點

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（`ResumeState` 加 `source`）
- Modify: `sentinel/src/career_sentinel/web/app.py`（upload 設 source、GET /api/resume 回 source、新 import104、移除 `/api/resume104/diagnose`＋`_Resume104DiagnoseReq`＋`GET /api/resume104`）
- Modify: `sentinel/tests/test_web_app.py`（移除 3 個過時 resume104 web 測試）
- Test: `sentinel/tests/test_web_import104.py`（新檔）

**Interfaces:**
- Consumes（既有）：`scraper.resume104.resume104_session() -> Resume104|None`、`resume104.flatten_for_diagnosis(r) -> str`、`runner.try_begin_browser()/end_browser()`、`store.load_resume/save_resume`。
- Produces：`ResumeState.source: str = ""`；`POST /api/resume/import104` → `{chars, resume104}`；`GET /api/resume` 回傳加 `source`。

- [ ] **Step 1: 寫失敗測試**

建立 `sentinel/tests/test_web_import104.py`：

```python
from fastapi.testclient import TestClient
from career_sentinel import store
from career_sentinel.web import app as webapp


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def _mock_104(monkeypatch, session_ret):
    from career_sentinel.web import runner
    from career_sentinel.scraper import resume104
    monkeypatch.setattr(runner, "try_begin_browser", lambda: True)
    monkeypatch.setattr(runner, "end_browser", lambda: None)
    monkeypatch.setattr(resume104, "resume104_session", lambda: session_ret)


def _r104(pii_text="姓名：王小明", exp_text="甲公司 後端"):
    from career_sentinel.models import Resume104, Resume104Block
    return Resume104(vno="v1", progress=90, blocks=[
        Resume104Block(id="info", label="基本資料", text=pii_text, is_pii=True, completed=True),
        Resume104Block(id="experience", label="工作經歷", text=exp_text, is_pii=False, completed=True),
    ])


def test_import104_sets_active_resume_and_strips_pii(tmp_path, monkeypatch):
    _mock_104(monkeypatch, _r104())
    c = _client(tmp_path)
    r = c.post("/api/resume/import104")
    assert r.status_code == 200
    body = r.json()
    assert body["chars"] > 0
    assert body["resume104"]["vno"] == "v1"
    # resume_text 只含非 PII、source=104
    conn = store.connect(tmp_path / "db.sqlite")
    st = store.load_resume(conn)
    assert st.source == "104"
    assert "甲公司" in st.resume_text
    assert "王小明" not in st.resume_text  # PII 未進 resume_text
    g = c.get("/api/resume").json()
    assert g["has_resume"] is True and g["source"] == "104"


def test_import104_not_logged_in_409(tmp_path, monkeypatch):
    _mock_104(monkeypatch, None)
    assert _client(tmp_path).post("/api/resume/import104").status_code == 409


def test_import104_busy_409(tmp_path, monkeypatch):
    from career_sentinel.web import runner
    monkeypatch.setattr(runner, "try_begin_browser", lambda: False)
    assert _client(tmp_path).post("/api/resume/import104").status_code == 409


def test_import104_empty_after_strip_400(tmp_path, monkeypatch):
    # 全 PII → 攤平為空 → 400
    from career_sentinel.models import Resume104, Resume104Block
    _mock_104(monkeypatch, Resume104(vno="v1", progress=10, blocks=[
        Resume104Block(id="info", label="基本資料", text="姓名：王", is_pii=True, completed=True),
    ]))
    assert _client(tmp_path).post("/api/resume/import104").status_code == 400


def test_upload_sets_source_upload(tmp_path):
    c = _client(tmp_path)
    c.post("/api/resume/upload", files={"file": ("r.txt", "履歷內容".encode("utf-8"), "text/plain")})
    assert c.get("/api/resume").json()["source"] == "upload"


def test_resume_get_default_source_empty(tmp_path):
    assert _client(tmp_path).get("/api/resume").json()["source"] == ""
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_web_import104.py -v`
Expected: FAIL（`404`：import104 不存在；`KeyError: 'source'`）

- [ ] **Step 3: models 加 source**

`sentinel/src/career_sentinel/models.py` 的 `ResumeState` 加欄位（放在 `diagnosis` 之後）：
```python
    source: str = ""   # "" | "upload" | "104"
```

- [ ] **Step 4: upload 設 source、GET 回 source**

`sentinel/src/career_sentinel/web/app.py`：
(a) `resume_upload` 內 `state.resume_text = text` 之後加 `state.source = "upload"`（在 `store.save_resume` 之前）。
(b) `resume_get` 回傳 dict 加 `"source": state.source`（與 `has_resume`/`chars` 等同層）。

- [ ] **Step 5: 新 import104 端點**

在 `resume_diagnose` 端點附近新增：
```python
    @app.post("/api/resume/import104")
    def resume_import104() -> dict:
        from ..scraper import resume104 as r104
        if not runner.try_begin_browser():
            raise HTTPException(status_code=409, detail="瀏覽器忙碌中（可能正在抓取），請稍候再試")
        try:
            r = r104.resume104_session()
        except Exception:
            raise HTTPException(status_code=502, detail="讀取 104 履歷失敗，請重試")
        finally:
            runner.end_browser()
        if r is None:
            raise HTTPException(status_code=409, detail="尚未登入，請先在終端機執行：career-sentinel login")
        text = r104.flatten_for_diagnosis(r)
        if not text.strip():
            raise HTTPException(status_code=400, detail="104 履歷內容為空（可能未填寫），無法匯入")
        conn = _conn()
        state = store.load_resume(conn)
        state.resume_text = text
        state.source = "104"
        store.save_resume(conn, state)
        return {"chars": len(text), "resume104": r.model_dump()}
```

- [ ] **Step 6: 移除舊 104 端點與其測試**

(a) `web/app.py`：刪除 `@app.get("/api/resume104")`（`resume104_get`）與 `@app.post("/api/resume104/diagnose")`（`resume104_diagnose`）兩個端點函式；刪除只被它們用到的請求模型 `_Resume104DiagnoseReq`（grep 確認無他處引用再刪）。
(b) `sentinel/tests/test_web_app.py`：刪除三個過時測試函式——讀 104 的 `test_resume104_get*`（含 GET `/api/resume104` 的兩個：成功版與 `test_resume104_get_busy_and_not_logged_in`）與 `test_resume104_diagnose_strips_pii`（POST `/api/resume104/diagnose`）。這些端點已移除、其 PII 覆蓋由 `test_web_import104.py` 取代。

> 注意：`sentinel/tests/test_resume104.py` 是 scraper 層測試（`parse_resume104_blocks`/`flatten_for_diagnosis_strips_pii` 等），**不要動**——那些函式仍在用。

- [ ] **Step 7: 跑測試確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_web_import104.py -v`
Expected: PASS（6 passed）

- [ ] **Step 8: 全測試回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠（已移除的 3 個 resume104 web 測試不再存在、不報 collection error）

- [ ] **Step 9: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_app.py sentinel/tests/test_web_import104.py
git commit -m "feat(sentinel): 履歷 source 欄 + /api/resume/import104 + 移除舊 104 端點（SP18）"
```

---

### Task 2: 前端 ProfilePage ＋ api.ts

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（新 `importResume104`；`ResumeState` 加 `source`）
- Create: `sentinel/web/frontend/src/ProfilePage.tsx`
- 驗證：`cd sentinel/web/frontend && npm run build`

**Interfaces:**
- Consumes：`/api/resume/import104`（Task 1）、既有 `uploadResume`/`diagnoseResume`/`getResume`/`openApplyPage`。
- Produces：`importResume104(): Promise<Response>`；`ResumeState.source: string`；`<ProfilePage />`（Task 3 掛載）。

- [ ] **Step 1: api.ts**

`sentinel/web/frontend/src/api.ts`：
(a) `ResumeState` interface 加 `source: string;`。
(b) 新增（放在 `getResume104` 附近或 resume 相關區）：
```typescript
export interface Resume104Import {
  chars: number;
  resume104: Resume104;
}

export async function importResume104(): Promise<Response> {
  return fetch("/api/resume/import104", { method: "POST" });
}
```
（`Resume104` 型別已存在於 api.ts。此步**不刪** `getResume104`/`diagnoseResume104`——它們仍被尚未刪除的 `Resume104Page.tsx` 使用，Task 3 刪頁時一併清。）

- [ ] **Step 2: 建立 ProfilePage**

建立 `sentinel/web/frontend/src/ProfilePage.tsx`：

```tsx
import {
  Badge, Button, FileInput, Grid, Group, List, NumberInput, Paper, SegmentedControl,
  Stack, Text, TextInput, ThemeIcon,
} from "@mantine/core";
import { IconAlertTriangle, IconCheck, IconLock, IconExternalLink } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  diagnoseResume, getResume, importResume104, openApplyPage, uploadResume, type Resume104,
} from "./api";
import BusyHint from "./BusyHint";
import { PageContainer, PageHeader } from "./ui";

export default function ProfilePage() {
  const qc = useQueryClient();
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [source, setSource] = useState("upload");
  const [title, setTitle] = useState("");
  const [salary, setSalary] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [importBusy, setImportBusy] = useState(false);
  const [importErr, setImportErr] = useState<string | null>(null);
  const [r104, setR104] = useState<Resume104 | null>(null);
  const [applyBusy, setApplyBusy] = useState(false);

  useEffect(() => {
    if (resume.data) {
      setTitle(resume.data.target_title);
      setSalary(resume.data.expected_salary ?? "");
    }
  }, [resume.data]);

  const sourceLabel = resume.data?.source === "104" ? "104 匯入"
    : resume.data?.source === "upload" ? "上傳檔案" : "";

  async function onUpload(file: File | null) {
    if (!file) return;
    setErr(null);
    const r = await uploadResume(file);
    if (!r.ok) { setErr("履歷上傳失敗（僅支援 PDF / TXT）"); return; }
    qc.invalidateQueries({ queryKey: ["resume"] });
  }

  async function runImport() {
    setImportErr(null); setImportBusy(true);
    try {
      const r = await importResume104();
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setImportErr(b.detail ?? "匯入失敗"); return; }
      setR104(b.resume104);
      qc.invalidateQueries({ queryKey: ["resume"] });
    } catch { setImportErr("網路錯誤，請重試"); }
    finally { setImportBusy(false); }
  }

  async function openEdit() {
    if (!r104?.vno) return;
    setImportErr(null); setApplyBusy(true);
    try {
      const r = await openApplyPage(`https://pda.104.com.tw/profile/edit?vno=${r104.vno}`);
      if (!r.ok) { const b = await r.json().catch(() => ({})); setImportErr(b.detail ?? "開啟失敗"); }
    } catch { setImportErr("網路錯誤，請重試"); }
    finally { setApplyBusy(false); }
  }

  async function runDiagnose() {
    setErr(null); setBusy(true);
    const r = await diagnoseResume(title, salary === "" ? null : Number(salary));
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "健檢失敗");
      return;
    }
    qc.invalidateQueries({ queryKey: ["resume"] });
  }

  const d = resume.data?.diagnosis;
  return (
    <PageContainer>
      <Stack gap="md">
        <PageHeader title="我的履歷" subtitle="上傳履歷或從 104 匯入，作為比對／客製化／健檢的依據" />

        <Paper bg="dark.6" radius="md" p="lg">
          <Stack>
            <SegmentedControl
              value={source}
              onChange={setSource}
              data={[{ label: "上傳檔案", value: "upload" }, { label: "從 104 匯入", value: "104" }]}
            />

            {source === "upload" && (
              <FileInput label="上傳履歷（PDF / TXT）" placeholder="選擇檔案" accept=".pdf,.txt" onChange={onUpload} />
            )}

            {source === "104" && (
              <Stack gap="sm">
                <Group>
                  <Button onClick={runImport} loading={importBusy}>從 104 匯入</Button>
                  {r104 && (
                    <Button size="compact-sm" variant="light" leftSection={<IconExternalLink size={15} />}
                      onClick={openEdit} loading={applyBusy}>開啟編輯頁</Button>
                  )}
                </Group>
                <BusyHint active={importBusy} label="讀取中" />
                {importErr && <Text c="danger.6" size="sm">{importErr}</Text>}
                {r104 && (
                  <Stack gap="sm">
                    <Badge variant="light" color="teal" w="fit-content">完成度 {r104.progress}%</Badge>
                    {r104.blocks.map((b) => (
                      <Paper key={b.id} bg="dark.7" radius="md" p="md">
                        <Group gap={8} mb="xs">
                          <Text fw={600} size="sm">{b.label}</Text>
                          {b.is_pii && <Badge size="xs" variant="light" color="gray" leftSection={<IconLock size={10} />}>個資（不送 LLM）</Badge>}
                          {b.completed && <Badge size="xs" variant="light" color="teal">已完成</Badge>}
                        </Group>
                        <Text size="sm" c="dark.1" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{b.text}</Text>
                      </Paper>
                    ))}
                  </Stack>
                )}
              </Stack>
            )}

            <Text size="sm" c="dimmed">
              {resume.data?.has_resume
                ? `已載入 ${resume.data.chars} 字${sourceLabel ? `（來源：${sourceLabel}）` : ""}`
                : "尚未設定履歷"}
            </Text>

            <Group grow>
              <TextInput label="目標職稱" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
              <NumberInput label="期望月薪（選填）" value={salary} onChange={(v) => setSalary(typeof v === "number" ? v : "")} />
            </Group>
            {err && <Text c="danger.6" size="sm">{err}</Text>}
            <Button onClick={runDiagnose} loading={busy} w="fit-content"
              disabled={!resume.data?.has_resume || !title.trim()}>
              執行健檢
            </Button>
            <BusyHint active={busy} label="分析中" />
          </Stack>
        </Paper>

        {d && (
          <Grid mt="md">
            <Grid.Col span={6}>
              <Paper bg="dark.6" radius="md" p="lg" h="100%">
                <Group gap={8} mb="sm">
                  <ThemeIcon variant="light" color="teal" size="sm"><IconCheck size={13} /></ThemeIcon>
                  <Text fw={600}>優勢</Text>
                </Group>
                <List size="sm" spacing={6}>{d.strengths.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
              </Paper>
            </Grid.Col>
            <Grid.Col span={6}>
              <Paper bg="dark.6" radius="md" p="lg" h="100%">
                <Group gap={8} mb="sm">
                  <ThemeIcon variant="light" color="amber" size="sm"><IconAlertTriangle size={13} /></ThemeIcon>
                  <Text fw={600}>待補強</Text>
                </Group>
                <List size="sm" spacing={6}>{d.gaps.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
              </Paper>
            </Grid.Col>
          </Grid>
        )}
      </Stack>
    </PageContainer>
  );
}
```

- [ ] **Step 3: 型別檢查 ＋ build**

Run（於 `sentinel/web/frontend`）：`npm run build`
Expected: 成功（ProfilePage 尚未被 import 是正常的——尚未被引用的檔案不會觸發 unused 錯誤；若某個 import 未用到，移除之）。

- [ ] **Step 4: 後端回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠（未動後端）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/ProfilePage.tsx
git commit -m "feat(sentinel): ProfilePage 我的履歷(上傳/104匯入合一)+api.ts（SP18）"
```

---

### Task 3: 導覽收斂 ＋ 移除舊履歷頁

**Files:**
- Modify: `sentinel/web/frontend/src/App.tsx`（resume div 換 ProfilePage、移除 Resume104Page）
- Modify: `sentinel/web/frontend/src/Sidebar.tsx`（PageKey/NAV：移除 resume104、resume 改名我的履歷）
- Modify: `sentinel/web/frontend/src/api.ts`（移除已無用的 `getResume104`/`diagnoseResume104`）
- Delete: `sentinel/web/frontend/src/ResumePage.tsx`、`sentinel/web/frontend/src/Resume104Page.tsx`
- 驗證：`cd sentinel/web/frontend && npm run build`

**Interfaces:**
- Consumes：`<ProfilePage />`（Task 2）。

- [ ] **Step 1: App.tsx 換頁**

`sentinel/web/frontend/src/App.tsx`：
- 移除 `import ResumePage from "./ResumePage";` 與 `import Resume104Page from "./Resume104Page";`，新增 `import ProfilePage from "./ProfilePage";`。
- 把 `resume` 的 `<div>` 內容從 `<ResumePage />` 改為 `<ProfilePage />`（`page === "resume"` key 不變）。
- 移除 `resume104` 的 `<div style={{ display: page === "resume104" ? … }}><Resume104Page /></div>`。

- [ ] **Step 2: Sidebar 導覽**

`sentinel/web/frontend/src/Sidebar.tsx`：
- `PageKey` 移除 `"resume104"`。
- `NAV`：`{ key: "resume", label: "履歷健檢", icon: IconFileText }` 的 label 改為 `"我的履歷"`；移除 `{ key: "resume104", label: "104 履歷", icon: IconId }` 那項；若 `IconId` 不再被使用，從 import 移除。

- [ ] **Step 3: api.ts 清理**

`sentinel/web/frontend/src/api.ts`：移除 `getResume104`、`diagnoseResume104` 兩個函式（Resume104Page 刪除後已無引用）。`Resume104`/`Resume104Block` 型別**保留**（ProfilePage 與 `importResume104` 的 `Resume104Import` 仍用）。

- [ ] **Step 4: 刪除舊頁**

```bash
git rm sentinel/web/frontend/src/ResumePage.tsx sentinel/web/frontend/src/Resume104Page.tsx
```

- [ ] **Step 5: 型別檢查 ＋ build**

Run（於 `sentinel/web/frontend`）：`npm run build`
Expected: 成功。若報殘留 import（ResumePage/Resume104Page/IconId、或 api.ts 移除函式後某型別 unused）清乾淨。

- [ ] **Step 6: 後端回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠。

- [ ] **Step 7: Commit**

```bash
git add -A sentinel/web/frontend/src/
git commit -m "feat(sentinel): 導覽 我的履歷 合一，移除 ResumePage/Resume104Page（SP18）"
```

---

## Self-Review 註記（計畫作者）

- **Spec coverage：** source 欄+import104+移除舊端點(Task1)、ProfilePage+api.ts(Task2)、導覽收斂+刪舊頁(Task3) 全覆蓋。
- **PII：** Task1 import104 用 `flatten_for_diagnosis`（只取非 PII 區塊）設 resume_text，測試 `test_import104_sets_active_resume_and_strips_pii` 斷言 PII 標記字串不在 resume_text；`resume104` 原始（含 PII）只回給前端顯示、不寫進 resume_text。
- **build 綠不中斷：** Task2 建 ProfilePage 但暫不刪舊頁、不刪 api.ts 舊函式（Resume104Page 仍用）→ build 綠；Task3 刪頁時才移除 api.ts 舊函式 → build 綠。順序自洽。
- **型別一致：** `importResume104`/`Resume104Import`/`ResumeState.source`（Task2 定義）→ ProfilePage(Task2)/App(Task3) 使用；`Resume104` 型別跨 api.ts/ProfilePage 一致。
- **測試移除：** Task1 移除 test_web_app.py 三個過時 resume104 web 測試（端點已刪），scraper 層 test_resume104.py 不動。
- **目標職稱/薪資：** 依 spec 留在 ProfilePage（SP19 再搬），diagnose 流程不變。
