# career-sentinel SP11：客製化履歷 + 求職信 設計

> 日期：2026-07-03。狀態：使用者已核可設計，待 plan。
> 前情：SP1–SP10 完成、219 測試綠。

## 範圍決策（使用者選定）

原 SP11 綁「客製化履歷/求職信/投遞/追蹤」四件，風險差異大，**分拆**：
- **本 SP＝客製化履歷＋求職信**（純本地 LLM 產出，安全、高價值）。
- **自動投遞→SP11b**（登入態寫入 104、端點未知、需先 spike，roadmap 記）。
- **追蹤**：已由儀表板「我的應徵」（applications 爬蟲）涵蓋，不重做。

## 目標

貼一個 104 職缺網址 → 針對該職缺產出「履歷客製化建議」＋「求職信全文」，
使用者可讀、編輯、複製使用。

## 關鍵決策（使用者選定）

- **觸發＝貼 104 網址**（重用 SP4 `jobfetch`；與 JD 比對同抓取路徑）。
- **產出＝建議要點 + 求職信全文**（履歷不重寫全文——避免 LLM 捏造事實；求職信是新文案）。

## 後端

### `tailor.py`（新模組）
- `tailor_application(resume_text: str, target_title: str, jd: JobDetail, *, client=None) -> TailoredApplication`：
  組 prompt（履歷全文＋JD 摘要＋目標職稱 → 要求輸出 ① 履歷客製化建議 ② 求職信全文）→
  `llm.parse_json(prompt, TailoredApplication, system=...)`（重用既有 provider-aware，
  今天日期由 `llm._with_today` 自動注入）。
- prompt 規則：履歷建議只給「要強調的重點／建議調整／該補的關鍵字」，**不要求重寫履歷全文、
  不得捏造使用者沒有的經歷**；求職信 300–400 字繁體中文、對應該職缺、語氣專業誠懇。

### 模型（`models.py`）
```python
class TailoredApplication(BaseModel):
    job_title: str = ""
    company: str = ""
    resume_tips: list[str] = []          # 要強調的重點
    resume_adjustments: list[str] = []   # 建議調整
    missing_keywords: list[str] = []     # 該補的關鍵字
    cover_letter: str = ""               # 求職信全文
```

### 端點（`web/app.py`）
- `POST /api/tailor` body `{job_url: str}`：
  - 重用 SP4：`jobfetch.extract_job_code(job_url)`（ValueError→400）、
    `jobfetch.fetch_job_detail(code)`（例外→502「抓取職缺失敗，請確認網址」）——同 `/api/match`。
  - 無履歷（`resume_text` 空）→ 400「請先上傳履歷」；無 LLM key → 400（RuntimeError 對映）。
  - `tailor_application` 成功回 `TailoredApplication.model_dump()`；RuntimeError→400、其他例外→500「生成失敗，請重試」。
  - **不快取**（履歷會變、每次要最新；一次 LLM 呼叫成本可接受）。

## 前端——新分頁「客製化」（第七個 Tab）

- `App.tsx` 加第七 Tab（value="tailor"，IconFileText 系或 IconWand）；沿用 AppShell 側欄。
- `TailorPage.tsx`：
  - 輸入：104 職缺網址 TextInput（同 MatchPage：leftSection、Enter 觸發）＋「客製化」主按鈕；
    未上傳履歷 → amber 提示引導到履歷健檢、按鈕 disabled。
  - 輸出（`PageContainer`）：
    - 頁首帶回填的 `job_title` · `company`。
    - 履歷客製化區：要強調重點（teal ThemeIcon）／建議調整（amber）／該補關鍵字（條列）。
    - **求職信**：`Paper bg="dark.6"`＋`whiteSpace: pre-wrap` 顯示全文，右上「複製」按鈕
      （`navigator.clipboard.writeText`，成功短暫顯「已複製」）。
  - 網路呼叫 try/finally 解鎖；錯誤 danger 顯示＋不清空輸入。
  - 不持久化（重載消失，同健檢/比對慣例）。
- `api.ts`：`TailoredApplication` 介面 ＋ `tailorApplication(job_url) -> Response`。

## 邊界（YAGNI／安全）

- **不碰投遞**（SP11b）、**不改 104 履歷**（SP12）、不快取、不做多版本比較、不匯出檔案。
- 履歷走「建議」非重寫全文 → 降低 LLM 捏造風險；求職信為新產出文案（人看過再用）。
- PII：送 LLM 履歷全文＋JD（與 SP3/SP4 同級，不新增出口類型）。

## 測試

- `tailor.py`：假 client 餵含 JSON 回應→解析驗證（全欄位）；壞 JSON→例外。
- 端點：無 job_url/壞網址→400、無履歷→400、無 key→400、抓取失敗→502、
  成功回全欄位（monkeypatch `jobfetch.fetch_job_detail`＋`tailor.tailor_application`）。
- 前端 build 零 TS 錯誤。
- 真機：貼一個面試中職缺網址→看客製化建議與求職信品質、複製鍵可用；未上傳履歷正確擋下。
