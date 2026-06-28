# Spike 發現：104 登入後三類資料的 XHR 端點與結構

> 以 rebrowser-playwright（headful）帶登入 profile 自動造訪三頁、攔截 JSON 回應得出。
> 所有端點都在 `pda.104.com.tw`（求職者中心），回應統一是 `{data, metadata}` 信封。
> 登入態靠專用 Chrome profile 的 session cookie（`JBCLOGIN`/`JBCSESS` 等）。
> **headless 過不了 Cloudflare、headful 才行**（`run` 本來就 headful）。

## 共通存取方式
- 造訪頁面 → rebrowser 攔 `page.on("response")`；或更省事：在已登入的 page context 內直接
  `page.request.get(<api>)`（同 session/cookie，回乾淨 JSON，免解析 DOM）。Phase 2 傾向後者。
- 信封：`{"data": <payload>, "metadata": {"pagination"?: {count,total,currentPage,lastPage}}}`。

---

## 1. 誰看過我（viewers）

- **頁面**：`https://pda.104.com.tw/work/peruseRecord`
- **資料端點**：`GET https://pda.104.com.tw/api/peruse-record/companies?page=1`
- **回應**：`data: [ 公司 ]`，**以公司為單位**彙整誰看過你。每筆關鍵欄位：

| 欄位 | 意義 | → `Viewer` |
|------|------|-----------|
| `custName` | 公司名 | `company` |
| `custNo` | 公司編號 | （存 raw） |
| `browseDate` | 看的時間（字串） | `viewed_at` |
| `jobCatTag.desc` | 看的職類描述 | `job_title`（公司層級，可能為職類非單一職缺） |
| `browseNos[]` | 被看的職缺編號 | （存 raw） |
| `mainScore` | 契合度分數 | （存 raw） |

- 分頁：`metadata.pagination`（`?page=N`）。
- 自然鍵建議：`(custName, jobCatTag.desc)`。

## 2. 訊息／面試邀約（messages）

- **頁面**：`https://pda.104.com.tw/work/message/chat`（會轉到 `/chat/exclusive`）
- **資料端點**：`GET https://pda.104.com.tw/api/messages/chatrooms?filter=exclusive&page=1&pageSize=20`
  - 另有 `filter=general`（一般訊息）。**兩個 filter 都要抓**。
- **回應**：`data: [ 對話室 ]`，每筆關鍵欄位：

| 欄位 | 意義 | → `Message` |
|------|------|------------|
| `chatroomId` | 對話室 id | `thread_id` |
| `custName` | 公司名 | `company` |
| `jobName` | 職缺名 | （存 raw） |
| `msg` | 最後一則訊息 | `last_message` |
| `msgDate` | 最後訊息時間 | （raw；可當排序） |
| `isRead` | 是否已讀（0/1） | （存 raw） |
| `lastEvent.{desc,type}` | 最後事件描述/類型 | 面試判斷依據 |

- **面試邀約**：104 把面試獨立成分類。`work/message/ajax/options` 的 `optionsMessageInterviewList`
  列出面試狀態：`coming` 未過期 / `pending` 待回報 / `attended` 已出席 / `absent` 未出席 / `canceled` 已取消。
  - MVP 判斷（待 Phase 2 用真實面試對話確認精準對應）：`has_interview_invite` ←
    `lastEvent.desc` 含「面試」或 `lastEvent.type` 對應面試類型。
  - `invite_date`（面試日期）：chatrooms 列表**未必直接帶**，可能要開對話室或打面試專屬端點。**Phase 2 待補**。
- 分頁：`metadata.pagination`。

## 3. 我的應徵（applications）

- **頁面**：`https://pda.104.com.tw/applyRecord/`
- **資料端點**：`GET https://pda.104.com.tw/applyRecord/ajax/list?page=1&status=all`
  - `status` 可帶 `all`（亦見 `notApply` 等）。
- **回應**：`{data: [ 應徵紀錄 ], metadata.pagination}`。
- ⚠️ **目前 `data: []`（使用者最近未投遞）→ item 結構未知。**
  - 預期欄位（依 104 慣例，待有資料時確認）：`jobNo`/`jobName`/`custName`/`applyDate`/`statusDesc`。
  - → `Application`：`job_id=jobNo`、`company=custName`、`title=jobName`、`status=statusDesc`、`applied_at=applyDate`（**待確認**）。

---

## Phase 2 待補（gaps）
1. **applications item 結構**：使用者目前無應徵紀錄，端點正確但 `data` 空。需在有投遞時再擷取一次確認欄位。
2. **面試邀約精準判斷 + 日期**：`chatrooms` 列表只到 `lastEvent`；面試「日期」可能要開對話室或面試專屬端點。
3. **viewers 的 job_title 粒度**：`peruse-record/companies` 是公司層級；若要單一職缺粒度需另找端點。
4. **取數方式**：建議 Phase 2 用 `page.request.get(<api>)`（已登入 context 直接打 JSON）取代 DOM 解析。

## 對應 fixture（去識別化，供 Phase 2 解析 TDD）
- `tests/fixtures/viewers.json`、`tests/fixtures/messages.json`、`tests/fixtures/applications_empty.json`
