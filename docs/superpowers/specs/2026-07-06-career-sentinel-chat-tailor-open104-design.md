# 聊天總指揮增能 B-#5：聊天客製化＋連 104 設計

**日期：** 2026-07-06
**狀態：** 設計定案，待實作

## 這是什麼

career-sentinel 聊天總指揮的增能項目 #5（LLM 花錢批的第一個）：讓 agent 在對話中幫使用者**寫客製化履歷與求職信**，寫完提供**直接連到 104 投遞頁**的按鈕。屬 SP21 分級的「LLM 花錢動作」，故用**提議＋按鈕卡**：agent 提議、使用者按下「客製化」才實際跑 tailor（成本在按下時）。

**利多：** `/api/tailor`（吃 url、抓 JD、跑 tailor、回客製化內容）與 `/api/apply/open`（開 104 投遞頁）**皆已存在**（JobCardDrawer/SP17 在用），前端 `tailorApplication`/`openApplyPage` 也在。本項幾乎不動後端。

同批較大的 #4（拖檔＋貼網址分析、非 104 通用抓取）另一個 spec。

## 目標

一句話：**讓 agent 在聊天提議 `tailor` 動作卡，使用者按下後前端直接呼叫既有 `/api/tailor` 產出客製化建議＋求職信並渲染在聊天，附「開 104 投遞頁」按鈕（既有 `/api/apply/open`）。**

## 現況（實作依據）

- **`/api/tailor`（app.py:252）**：`_MatchReq{job_url}` → `extract_job_code` → `fetch_job_detail` → `tailor.tailor_application(resume_text, target_title, jd)` → `result.model_dump()`。回 `TailoredApplication`（job_title/company/resume_tips/resume_adjustments/missing_keywords/cover_letter）。未上傳履歷→400「請先上傳履歷」；壞網址→400；抓取失敗→502；生成失敗→500。
- **`/api/apply/open`（app.py:276）**：`_MatchReq{job_url}` → `runner.try_begin_browser()`（忙碌→409）→ `apply.open_job_page(url)`（在專案登入態 Chrome 開 104 頁；找不到 Chrome→500）→ `{status:"opened"}`。**只開頁、不代填代送**。
- **前端 api.ts**：`tailorApplication(job_url) -> Promise<Response>`；`openApplyPage(job_url) -> Promise<Response>`；`TailoredApplication` 型別（job_title/company/resume_tips/resume_adjustments/missing_keywords/cover_letter）。
- **`ChatPage.tsx`**：建議渲染 `{m.suggestions?.map((s, j) => <SuggestionCard key={j} s={s} />)}`（約 234 行）；`SuggestionCard` 呼叫 `applyUpdate(s)`（`/api/chat/apply`）。`SuggestedUpdate` 已有 `payload`（SP21）。
- **`chat.py` `_CONTRACT`**：定義 `<suggestions>` 格式與允許的 field/op（含 SP21 的管道動作 track/job_offer/... 走 payload）。SSE 端把 `field != "memory"` 的建議當卡片送前端（`cards`）。
- **`JobCardDrawer.tsx`（SP17）**：既有 tailor 結果渲染（要強調的重點/建議調整/該補關鍵字/求職信可複製）＋「開啟投遞頁」——本項的 TailorCard 呈現比照它。

## 機制（重用既有端點，零新後端端點）

- agent 判斷使用者要客製化某職缺時，在 `<suggestions>` 提議 `tailor` 動作：
  ```json
  {"field": "tailor", "op": "run", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師"}}
  ```
  這是**提議**——agent 不自行執行、不宣稱已完成。
- SSE 端既有邏輯把 `field != "memory"` 的建議送成 `cards`；`tailor` 自然成為一張卡（無需改 SSE 骨架）。
- **`tailor` 不走 `/api/chat/apply`／`apply_update`**（那是 mutation 用）；前端 TailorCard 直接呼叫既有 `/api/tailor`。故 `apply_update`/`ALLOWED` **不加 tailor**、不改。

## 後端變更（唯一：`chat.py` 合約文字）

`_CONTRACT` 加 `tailor` 提議說明與範例（放在管道動作規則之後）：

- 範例 items 加一行：
  ```json
  {"field": "tailor", "op": "run", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師"}}
  ```
- 規則補述：`tailor`＝提議「幫這個職缺客製化履歷與求職信」。**需使用者已上傳履歷**；`payload.code` 必來自 `get_pipeline`/`search_jobs`/`get_job_detail` 實際結果，不得杜撰；這是**提議**，會等使用者按下「客製化」才實際生成（花 LLM 錢），**agent 不要自行生成客製化內容或聲稱已完成**——只丟提議卡。

（`build_system_prompt` 回傳 `head + _CONTRACT`，故合約更新即生效；工具說明段不動。）

## 前端變更（`ChatPage.tsx` ＋ 新 `TailorCard`）

### 建議渲染分支

把 `{m.suggestions?.map((s, j) => <SuggestionCard key={j} s={s} />)}` 改為依 field 分派：

```tsx
{m.suggestions?.map((s, j) =>
  s.field === "tailor"
    ? <TailorCard key={j} payload={s.payload as { code: string; company?: string; title?: string }} />
    : <SuggestionCard key={j} s={s} />
)}
```

### 新 `TailorCard` 元件（`ChatPage.tsx` 內，比照 SuggestionCard 樣式）

- props：`payload: { code: string; company?: string; title?: string }`。
- 由 code 組 url：`const url = `https://www.104.com.tw/job/${payload.code}`;`。
- 初始：顯示「客製化 {company} · {title}」＋「客製化」`Button`。
- 按「客製化」→ `setBusy(true)` → `tailorApplication(url)`：
  - `!r.ok` → 讀 `body.detail` 顯示（如「請先上傳履歷」）。
  - `r.ok` → `setResult(body as TailoredApplication)`。
- 有 result 後渲染（比照 JobCardDrawer 客製化區）：要強調的重點（resume_tips）、建議調整（resume_adjustments）、該補的關鍵字（missing_keywords）、**求職信（cover_letter，可複製）**；再加「**開 104 投遞頁**」`Button` → `openApplyPage(url)`：
  - `!r.ok` → 讀 `body.detail`（如 409「瀏覽器忙碌中…」）顯示。
  - `r.ok` → 顯示「已在瀏覽器開啟投遞頁」。
- 錯誤/忙碌狀態沿用既有 r.ok 檢查與 BusyHint/loading 慣例。

（`tailorApplication`/`openApplyPage`/`TailoredApplication` 皆 api.ts 既有，import 進 ChatPage；複製求職信可用 `navigator.clipboard.writeText`，比照 JobCardDrawer。）

## Global Constraints（實作時必守）

- **成本把關**：tailor 只在使用者按下「客製化」時才跑（前端呼叫 /api/tailor 才產生 LLM 成本）；agent 只丟提議卡、不自行生成、不宣稱已完成。
- **agent 不寫入 104**：「開 104 投遞頁」只呼叫既有 `/api/apply/open`（在登入態 Chrome 開頁），由使用者親手投遞；不代填代送。
- **重用、零新後端端點**：直接用既有 `/api/tailor`、`/api/apply/open`；**不改 `apply_update`/`ALLOWED`**（tailor 不走 chat/apply）。
- **需履歷**：未上傳履歷時 /api/tailor 回 400，TailorCard 顯示該訊息（不崩）。
- **相容**：`tailor` 為新的建議 field，前端分派新增、既有 SuggestionCard（prefs/管道動作/memory）行為不變；`SuggestedUpdate.payload` 已在（SP21），後端 SSE 骨架不動。
- 後端測試用專案 venv；前端 `npm run build` 必過。

## 測試策略

- **`build_system_prompt` / `_CONTRACT`**（後端）：新測試斷言 prompt 含 `tailor`（agent 知道可提議客製化動作）；既有合約/管道動作測試維持綠。
- **`parse_suggestions`**（後端，既有機制）：解析含 `{"field":"tailor","op":"run","payload":{"code":...}}` 的 `<suggestions>` → 得到 field=="tailor"、payload.code 正確的 `SuggestedUpdate`（驗證 tailor 提議能被正確解析成卡片資料）。
- **`apply_update` 不誤收 tailor**（後端）：`apply_update(conn, SuggestedUpdate(field="tailor", op="run", payload={"code":"x"}))` 回 `ok=False`（落到 fallback「不允許」）——確認 tailor 不會被當 mutation 誤套用（防呆；正常流程前端不會這樣打）。
- **前端**：無單元測試，靠 `npm run build` ＋人工（客製化按鈕跑 /api/tailor、開 104 鈕跑 /api/apply/open、未上傳履歷/409 錯誤顯示）；契約由既有 /api/tailor、/api/apply/open 測試守。

## 明確不做（Out of Scope）

- #4：拖檔上傳分析、貼網址分析、非 104 通用抓取 → 下一個 spec。
- match/比對、公司研究、履歷健檢接進聊天 → 不在本項（花錢動作，若要另議）。
- 把 tailor 結果寫進 tracked_jobs 快取（JobCardDrawer 有做；聊天版本先不快取，每次按重跑）。
- agent 代填/代送 104；自動（不按鈕）跑 tailor。
