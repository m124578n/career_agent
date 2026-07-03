# career-sentinel SP11b：半自動投遞（開頁＋帶文案）設計

> 日期：2026-07-04。狀態：使用者已核可設計，待 plan。
> 前情：SP1–SP11 完成、225 測試綠。SP11 客製化履歷/求職信已上線。

## 關鍵安全模型（使用者核可）

**agent 全程不寫入 104。** 半自動投遞 = agent 用登入態純 Chrome 開啟該職缺頁、
把客製化求職信擺在 UI 供複製；**真正的「送出應徵」由使用者在真瀏覽器親手完成**
（人在真正送出點把關）。

**因此不必逆向 104 投遞端點**——我們從不 POST、不填表、不碰投遞 API，只用
`subprocess.Popen` 開一個網址（同既有 `login` 機制）。原 roadmap「需先 spike 投遞端點」
的前提（full-auto API 逆向）已被此模型取消；風險從高降到低。

## 關鍵決策（使用者選定）

- **自動化程度＝半自動（agent 開到投遞頁、使用者按送出）。**
- **填表方式＝開頁＋UI 帶文案供複製**（agent 不自動填、不 POST；受 rebrowser patch 卡手動操作
  的硬限制驅動——純 Chrome 可手動但不能自動填、rebrowser 能自動填但卡住手動送出，故選純 Chrome）。
- **觸發點＝客製化分頁接續**（SP11 產完求職信後「開啟投遞頁」）。

## 後端

### 端點 `POST /api/apply/open`（`web/app.py`）
- body `{job_url: str}`。
- 流程：
  1. `job_url` 空 → 400「請提供職缺網址」。
  2. `runner.try_begin_browser()`：若忙碌（scrape/recommend 進行中）→ 409
     「瀏覽器忙碌中（可能正在抓取），請稍候再試」。
  3. `browser.find_chrome()`：無 → `end_browser()` 後 500「找不到 Google Chrome，請確認已安裝」。
  4. `subprocess.Popen([chrome, f"--user-data-dir={profile}", "--no-first-run",
     "--no-default-browser-check", job_url])`（同 `cli._cmd_login` 機制、專案 profile 帶登入態）。
  5. `end_browser()`（旗標只守 launch 瞬間，不持有到使用者關閉 Chrome）。
  6. 回 `{"status": "opened"}`。
- **不 POST、不填表、不碰投遞 API、不新增爬蟲/資料表。**
- 抽一個小 helper `web/apply.py`：`open_job_page(job_url) -> None`（find_chrome＋Popen，
  供端點呼叫與單測 monkeypatch），保持 app.py 精簡。

### 追蹤
- 投遞後的追蹤由既有 applications 爬蟲＋儀表板「我的應徵」涵蓋——使用者手動應徵後，
  下次「重新抓取」自動出現在應徵清單。**SP11b 不做投遞紀錄表。**

## 前端——客製化分頁接續（`TailorPage.tsx`）

- SP11 客製化結果（求職信 Paper）下方加「**開啟投遞頁**」按鈕（tangerine 主動作）＋
  提示文字：「將用你的登入態 Chrome 開啟該職缺頁，請在瀏覽器中親手應徵、貼上求職信並送出。」
- 需保留觸發時的 `job_url`（TailorPage 已有輸入的 url state；用它呼叫 `/api/apply/open`）。
- 流程：客製化 → 複製求職信（既有鍵）→ 開啟投遞頁 → 在 Chrome 貼上、親手送出。
- 錯誤：409 忙碌／500 找不到 Chrome → 頁內 danger 顯示；按鈕 loading／try-finally 解鎖。
- `api.ts`：`openApplyPage(job_url) -> Response`。

## 邊界與安全

- **agent 不寫入 104**（送出由使用者親手）。
- 瀏覽器序列化：投遞開 Chrome 與 scrape/recommend 共用 `try_begin_browser` 旗標守 launch 瞬間。
  **已知殘餘邊界**：使用者手動開著投遞 Chrome 時若又觸發 scrape，rebrowser 會撞
  SingletonLock（scrape 端報錯、不靜默壞）——單人工具可接受，不加額外鎖。
- **殺 Chrome 注意（沿用專案鐵律）**：除錯時只殺本專案 profile 的 Chrome，別 `taskkill /IM chrome.exe`。
- 不做（YAGNI）：自動填表、投遞 API 逆向、投遞紀錄表、批次投遞、JobRow 投遞鈕
  （本輪只客製化分頁觸發）。

## 測試

- 端點（`web/apply.py` + `/api/apply/open`）：無 job_url→400、忙碌（`try_begin_browser` 回 False）→409、
  找不到 Chrome（`find_chrome` 回 None）→500、成功→`{status:"opened"}` 且
  `try_begin_browser`/`end_browser` 有成對呼叫、`subprocess.Popen` 收到 chrome 路徑＋job_url。
  **全 monkeypatch，不真的開 Chrome、不真的碰 104。**
- 忙碌路徑須驗證 `end_browser` **不被呼叫**（未 begin 就不該 end）；成功與 no-chrome 路徑
  驗證 `end_browser` **有**呼叫（begin 成功後必 end）。
- 前端 build 零 TS 錯誤。
- 真機：客製化一個職缺 → 點「開啟投遞頁」→ 登入態 Chrome 開該職缺頁、看得到應徵按鈕
  → 貼上求職信、親手送出 → 下次重新抓取該職缺出現在「我的應徵」。
