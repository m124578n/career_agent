# 設計規格：career-sentinel Phase 2 — 三個真 104 爬蟲

- 日期：2026-06-28
- 範圍：`sentinel/`（地端 career-sentinel）；把假爬蟲換成真的，讓 `run` 讀真實 104 登入後資料
- 狀態：設計已確認，待寫實作計畫
- 前置：Phase 1（管線骨架）完成；spike 已定位端點與結構（見 `sentinel/spike/FINDINGS.md`）

## 背景與目標

Phase 1 蓋好端到端管線，但 `cli._cmd_run` 接的是 `scraper/fake.py` 假資料。spike 已用真機驗證：
純 Chrome 登入 → profile 存 session → rebrowser headful 自動讀能過 Cloudflare → 攔到三類資料的
JSON API，且結構已確認（含使用者實投一筆後的應徵 item）。

本案把假爬蟲換成**三個真爬蟲**，讓 `career-sentinel run` 真正讀「誰看過我／投遞狀態／訊息（面試邀約）」，
存快照、比對變化、LLM 彙整。

### MVP 範圍（已與使用者確認）

- **每類只抓第 1 頁**（誰看過我／訊息約 20–30 筆、應徵全部）。全分頁留後續；diff 照樣抓新增/變動。
- **面試只標記有無**（`has_interview_invite`），不鑽「確切日期」（精準日期 + 自動進行事曆是後面獨立子專案）。
- 訊息兩個 filter（`exclusive` + `general`）都抓。
- 加 per-reader 容錯（最終 review Important #2）。

### 非目標（Out of scope）

- 全分頁逐頁抓、面試確切日期、行事曆整合、對話式履歷、公司評價 web 研究。
- 更細的應徵狀態（邀面試/婉拒需跨訊息頁判斷）——本案只到「已送出/已讀/公司已回覆」。
- 不改 Phase 1 的 store/diff/digest/models 既有行為（除新增 `failed_readers` 相關）。

## 技術選型

- 取數：navigate 進 104 頁（過 Cloudflare、`browser.wait_until_ready`）後，用
  **`page.request.get(<api>)`** 在已登入 context 內直接打 JSON 端點（比攔截乾淨、不依賴 DOM）。
  若端點被 Cloudflare 擋 → 該讀取器失敗、走容錯。
- 沿用 Phase 1 的 rebrowser-playwright（headful）、models、store、diff、digest。

## 模組結構

抓取與解析分離：解析是吃 `dict`（已解 JSON）回型別模型的純函式，用 `tests/fixtures/*.json` 單測；
`fetch_*` 需真瀏覽器、不單測。

| 檔案 | 職責 | 對外介面 |
|------|------|---------|
| `scraper/viewers.py` | 誰看過我 | `VIEWERS_URL`、`parse_viewers(data: dict) -> list[Viewer]`、`fetch_viewers(page) -> list[Viewer]` |
| `scraper/applications.py` | 投遞狀態 | `APPLICATIONS_URL`、`derive_status(item: dict) -> str`、`parse_applications(data: dict) -> list[Application]`、`fetch_applications(page) -> list[Application]` |
| `scraper/messages.py` | 訊息/面試 | `MESSAGES_URLS: list[str]`、`has_interview(item: dict) -> bool`、`parse_messages(data: dict) -> list[Message]`、`fetch_messages(page) -> list[Message]` |
| `scraper/real.py` | 編排 | `scrape(page) -> tuple[Snapshot, set[str]]` |

`scraper/fake.py` 保留（`run_pipeline` 單測用）。

## 端點與欄位對應（依 FINDINGS）

### viewers — `GET https://pda.104.com.tw/api/peruse-record/companies?page=1`
- `data: [item]`，每筆：`company=custName`、`job_title=jobCatTag.desc`、`viewed_at=browseDate`，`raw=item`。
- 自然鍵 `(company, job_title)`。

### applications — `GET https://pda.104.com.tw/applyRecord/ajax/list?page=1&status=all`
- `data: [item]`，每筆：`job_id=str(jobNo)`、`company=custName`、`title=jobName`、`applied_at=applyDate`、
  `status=derive_status(item)`，`raw=item`。
- `derive_status(item)`（純函式）：
  - `custReplyDate` 非空 或 `hrReplyCount>0` → `"公司已回覆"`
  - 否則 `custCheckDate` 非空 → `"已讀"`
  - 否則 → `"已送出"`

### messages — `GET https://pda.104.com.tw/api/messages/chatrooms?filter={exclusive,general}&page=1&pageSize=20`
- 兩個 filter 各打一次，合併。每筆：`thread_id=chatroomId`、`company=custName`、`last_message=msg`、
  `has_interview_invite=has_interview(item)`、`invite_date=None`，`raw=item`。
- `has_interview(item)`（純函式，啟發式）：`"面試"` 出現在 `item.lastEvent.desc` 或 `item.msg`。

## 資料流（`scraper.real.scrape`）

```
scrape(page):
    establish_session(page)          # goto 104 首頁 + wait_until_ready（取得 cf_clearance）
    failed = set()
    for name, fetch in [("viewers",fetch_viewers),("applications",fetch_applications),("messages",fetch_messages)]:
        try: results[name] = fetch(page)
        except Exception: failed.add(name)
    return Snapshot(viewers, applications, messages), failed
```

`fetch_*`：`resp = page.request.get(url)` → `resp.json()` → `parse_*`。messages 打兩個 filter URL 合併。

## 錯誤處理（容錯）

- **單一讀取器失敗** → 記進 `failed_readers`；該類**沿用上次快照的資料**（不寫空），避免下次 diff
  把整類誤判為新（最終 review Important #2 的污染問題）。沿用在 pipeline 層做（見下）。
- **未登入 / session 過期** → `establish_session` 後若被導去登入頁 → 回傳特殊狀態，`run` 印
  「請先 `career-sentinel login`」並中止（不寫壞快照）。
- **Cloudflare 未通過** → `wait_until_ready` 逾時 → 讀取器多半失敗 → 走容錯並回報。

### pipeline 接線（`cli`）

- `_cmd_run`：把 pipeline 呼叫移進 `with sync_playwright()` 區塊（修 Phase 1 標記的 ctx 順序），
  改呼叫 `scraper.real.scrape(page)`。
- `run_pipeline` 簽章擴充以吃 `failed_readers` 與「上次快照」：失敗類沿用上次快照同類資料後再存；
  報告字串結尾附「⚠️ 本次未讀到：<失敗類>（沿用上次）」。
- `run_pipeline` 仍接受可注入的 `scrape`，假爬蟲（回空 failed set）續供單測。

## 測試

- **純解析**（對 `tests/fixtures/*.json`）：`parse_viewers`、`parse_applications`、`parse_messages`，
  斷言欄位對應正確、筆數正確。
- **`derive_status`**：三情境（已送出／已讀／公司已回覆）。
- **`has_interview`**：`lastEvent.desc="面試邀約"`→True、`"已回覆"`→False、`msg` 含「面試」→True。
- **容錯沿用**：`run_pipeline` 給一個「viewers 失敗」的情境，斷言新快照 viewers 沿用上次、diff 不誤報。
- **`fetch_*`**：需真瀏覽器、不單測——以一次真機 `run` 驗證（登入態仍在）。
- 沿用 pytest；Phase 1 既有測試不得回歸。

## 開放問題（實作時釐清，不阻擋設計）

- `page.request.get` 對這三個 API 是否需額外 header（Referer/X-Requested-With）才不被擋——真機試，
  不行就退回「navigate 該頁 + 攔截」。
- 應徵「公司已回覆」是否要再細分邀面試/婉拒——本案不做，留後續。

## 後續

Phase 2 完成後，`run` 即讀真實 104 資料。再來的子專案（各自 spec→plan）：每日彙整報告強化、
行事曆整合（面試確切日期 + 自動進 Google Calendar）、對話式履歷整理、全分頁、自動排程。
