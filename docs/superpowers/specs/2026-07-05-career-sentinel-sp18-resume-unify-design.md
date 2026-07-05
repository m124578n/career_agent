# SP18：履歷合一 設計

**日期：** 2026-07-05
**狀態：** 設計定案，待實作

## 這是什麼

career-sentinel 求職流水線第四個子專案。把兩個履歷入口——`履歷健檢`（上傳 PDF/TXT）與 `104 履歷`（讀線上真實履歷）——合成一個「我的履歷」頁，採**單一「作用中履歷」**模型：來源可選（上傳檔案／從 104 匯入），兩者都成為驅動健檢/比對/客製化的同一份 `resume_text`。

roadmap（SP18 拆分後）：SP15 ✅ → SP16 ✅ → SP17 ✅ → **SP18（本篇）履歷合一** → SP19 偏好集中 → SP20 offer 比較 → SP21 聊天當總指揮。

> 偏好集中（目標職稱/薪資/地點等散落欄位收進單一 `JobPreferences`）是 **SP19**，不在本 SP。SP18 的「我的履歷」頁**暫時保留**目標職稱／期望薪資輸入（健檢需要），SP19 再把它們搬進偏好區。

## 目標

一句話：**兩個履歷入口合成一個「我的履歷」頁，單一作用中 `resume_text`，來源可為上傳檔案或從 104 匯入（去 PII 攤平）。**

## 現況（實作依據）

- **`ResumeState`（models.py）**：`resume_text`、`target_title`、`expected_salary`、`diagnosis`。
- **`POST /api/resume/upload`**：`resume.parse_resume(filename, bytes)` → 存 `resume_text`，回 `{chars}`。
- **`POST /api/resume/diagnose`**（`_DiagnoseReq{target_title, expected_salary}`）：用 `state.resume_text` ＋ target/salary → `diagnosis.diagnose(...)`，存 target/salary/diagnosis，回 diagnosis。
- **`GET /api/resume`**：回 `{has_resume, chars, target_title, expected_salary, diagnosis}`。
- **`GET /api/resume104`**：`resume104.resume104_session()`（需登入態 headful 瀏覽器）讀 104 履歷 → 回 `Resume104{vno, progress, blocks[]}`；未登入回 409。用 `runner.try_begin_browser()`/`end_browser()` 圍住。
- **`POST /api/resume104/diagnose`**：把 `Resume104` 攤平（`flatten_for_diagnosis`，只取非 PII 區塊）→ 健檢。
- **`scraper/resume104.py`**：`resume104_session() -> Resume104 | None`（None=未登入）、`flatten_for_diagnosis(r) -> str`（`"\n\n".join(【label】\ntext for 非 PII 且 text 非空)`）。
- **`Resume104Block`**：`id/label/text/is_pii/completed`；PII 區塊 `is_pii=True`，**不送 LLM**。
- **前端**：`ResumePage.tsx`（上傳＋目標/薪資＋健檢＋優勢/待補強）；`Resume104Page.tsx`（讀 104→區塊檢視含 PII 徽章、完成度、開編輯頁、104 健檢）。導覽 `Sidebar.tsx` 有 `resume`（履歷健檢）與 `resume104`（104 履歷）兩項；`App.tsx` 各自掛載。

## 後端變更

### 1. `ResumeState` 加 `source`（`models.py`）

```python
class ResumeState(BaseModel):
    resume_text: str = ""
    target_title: str = ""
    expected_salary: int | None = None
    diagnosis: ResumeDiagnosis | None = None
    source: str = ""   # "" | "upload" | "104"（作用中履歷來源）
```

`ResumeState` 以單列 JSON 存（`store.save_resume`/`load_resume` 用 `model_dump_json`/`model_validate_json`），新增欄位天然向後相容（舊 JSON 無此欄→預設 `""`），不需遷移。

### 2. `POST /api/resume/upload` 設 source（`web/app.py`）

既有邏輯後補一行 `state.source = "upload"`（存檔前）。回傳不變（`{chars}`）。

### 3. 新 `POST /api/resume/import104`（`web/app.py`）

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

- 回傳含 `resume104`（`{vno, progress, blocks}`）供前端顯示區塊與開編輯頁；`resume_text` 只存去 PII 的攤平文字（PII 不進 `resume_text`、不進 DB 的履歷文字欄）。

### 4. `GET /api/resume` 回 `source`

`resume_get` 回傳 dict 加 `"source": state.source`。

### 5. 移除 `POST /api/resume104/diagnose`

合一後健檢統一走 `/api/resume/diagnose`（作用中 `resume_text`）。刪除 `/api/resume104/diagnose` 端點與其請求模型 `_Resume104DiagnoseReq`（若無其他引用）。`GET /api/resume104`（純讀區塊）可保留亦可移除——本 SP 以 `import104` 回傳的 `resume104` 取代其在前端的用途，故**移除** `GET /api/resume104` 端點以免死碼（確認前端改用 import104 後無他處引用）。

## 前端變更

### 6. 新「我的履歷」頁（`ProfilePage.tsx`，取代 ResumePage＋Resume104Page）

- `PageHeader` title「我的履歷」、subtitle「上傳履歷或從 104 匯入，作為比對／客製化／健檢的依據」。
- **來源切換** `SegmentedControl`（`上傳檔案` | `從 104 匯入`）。
- **上傳檔案**：`FileInput`（accept `.pdf,.txt`，沿用 ResumePage 上傳邏輯 `uploadResume`）；成功後 invalidate `resume`。
- **從 104 匯入**：
  - 「從 104 匯入」按鈕 → `POST /api/resume/import104`（`BusyHint`「讀取中」）；成功後把回傳 `resume104` 存 local state 顯示區塊，並 invalidate `resume`。
  - 區塊檢視：沿用 Resume104Page 的呈現（每區塊 `Paper`，PII 徽章「個資（不送 LLM）」、完成度 Badge、`whitespace: pre-wrap`）。
  - 「開啟編輯頁」按鈕（`openApplyPage("https://pda.104.com.tw/profile/edit?vno=" + vno)`，沿用既有 apply/open 流程）。
- **作用中履歷狀態列**：顯示 `已載入 N 字`＋來源標示（`來源：上傳檔案` / `來源：104 匯入` / `尚未設定履歷`），讀 `GET /api/resume` 的 `has_resume/chars/source`。
- **目標職稱／期望薪資** `TextInput`/`NumberInput`（沿用 ResumePage，seed 自 `GET /api/resume`）＋**健檢**按鈕（`/api/resume/diagnose`，`BusyHint`「分析中」）＋優勢（teal）/待補強（amber）Grid。**SP18 保留於本頁**；SP19 再搬進偏好區。
- 視覺沿用 Cockpit 主題與既有 `PageContainer`/`PageHeader`/`Paper bg="dark.6"`/`BusyHint`。

### 7. api.ts

- 新 `importResume104(): Promise<Response>`（`POST /api/resume/import104`）。
- `ResumeState` 型別加 `source: string`。
- 移除已無用的 `getResume104`/`diagnoseResume104`（若 ProfilePage 不再用；確認無他處引用後刪）。既有 `openApplyPage` 保留（開編輯頁用）。

### 8. 導覽收斂（`Sidebar.tsx` ＋ `App.tsx`）

- `Sidebar.tsx`：`PageKey` 移除 `"resume104"`；`resume` 那項 label 由「履歷健檢」改為「我的履歷」（icon 沿用 `IconFileText`）；移除 `104 履歷` 項（`IconId` 若不再用一併移除 import）。
- `App.tsx`：移除 `Resume104Page` import 與其 `<div>`；把 `resume` 的 `<div>` 內容從 `<ResumePage/>` 換成 `<ProfilePage/>`（`page` key 仍用 `"resume"`）。
- 刪除 `ResumePage.tsx`、`Resume104Page.tsx`。

## Global Constraints（實作時必守）

- **PII 不外流**：104 履歷的 PII 區塊（`is_pii=True`）只在瀏覽器本地顯示；`resume_text`（進 DB、送 LLM）一律為 `flatten_for_diagnosis` 去 PII 後的文字。import104 絕不把 PII 寫入 `resume_text`。
- **讀 104 需登入態瀏覽器**：`import104` 沿用 `runner.try_begin_browser()/end_browser()` 圍住 `resume104_session()`；未登入回 409（沿用既有文案「尚未登入，請先在終端機執行：career-sentinel login」）；瀏覽器忙碌回 409。不寫入 104。
- **單一作用中履歷**：上傳或 104 匯入都覆寫同一份 `resume_text` 並設 `source`；健檢/比對/客製化統一用這份（比對/客製化端點讀 `state.resume_text` 的既有行為不變）。
- **相容**：`ResumeState` 加 `source` 為加法式（舊 JSON 無此欄→`""`），不需遷移；`/api/resume/upload`、`/api/resume/diagnose`、`/api/match`、`/api/tailor` 回傳與行為不變（只多存/回 source）。
- 後端綁 `127.0.0.1`；前端 `npm run build`（noUnusedLocals）必過（刪頁後清乾淨殘留 import）。

## 測試策略

- **`POST /api/resume/import104`**（mock `resume104.resume104_session` 與 `runner.try_begin_browser`）：
  - 回一個含 PII 與非 PII 區塊的 `Resume104` → `resume_text` 只含非 PII 攤平文字、`source="104"`、回傳 `chars` 與 `resume104`。
  - `resume104_session` 回 None（未登入）→ 409。
  - 攤平後為空（全 PII 或全空）→ 400。
  - `try_begin_browser` False（忙碌）→ 409。
- **`POST /api/resume/upload`**：上傳後 `GET /api/resume` 的 `source == "upload"`。
- **`GET /api/resume`**：回傳含 `source`（預設 `""`）。
- **PII 斷言**：import104 後 `store.load_resume().resume_text` 不含任何 PII 區塊文字（用一個 PII 區塊文字當標記字串斷言不出現）。
- **前端**：無單元測試，靠 `npm run build` ＋人工；契約由後端測試守。

## 明確不做（Out of Scope）

- 偏好集中（target_title/expected_salary/keywords 搬進單一 `JobPreferences`）→ **SP19**（本 SP 目標職稱/薪資仍留在我的履歷頁）。
- offer 比較 → SP20；聊天當總指揮 → SP21。
- SP17 遺留的 3 個技術債 Minor（app.py 死 import、卡片 prefill r.ok、空 Anchor）——可在本 SP 開場順手清或獨立 commit，非本 SP 核心。
- 既有 UI/UX 精修（window.alert、a11y 等）。
