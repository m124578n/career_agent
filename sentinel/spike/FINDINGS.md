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
- **回應**：`{data: [ 應徵紀錄 ], metadata.pagination}`。已用真實投遞確認 item 結構：

| 欄位 | 意義 | → `Application` |
|------|------|----------------|
| `jobNo` (int) | 職缺編號 | `job_id`（轉 str） |
| `jobName` (str) | 職缺名 | `title` |
| `custName` (str) | 公司名 | `company` |
| `applyDate` (str) | 投遞時間 `YYYY/MM/DD HH:MM:SS` | `applied_at` |
| `custCheckDate` (str) | 公司看過的時間（空=未讀） | 推導 `status` |
| `custReplyDate` (str) | 公司回覆時間 | 推導 `status` |
| `hrReplyCount` (int) | HR 回覆次數 | 推導 `status` |
| `autoNo`/`jobUrl`/`custUrl`/`replyReminder{day,type}`/… | 其他 | 存 raw |

- ⚠️ **無單一 `statusDesc` 欄位——投遞狀態要「推導」**：
  - `custCheckDate` 空 → 已送出/未讀；有值 → **已讀**。
  - `custReplyDate` 有值 → **公司已回覆**（是否邀面試/婉拒，需再對照訊息頁
    `chatrooms.lastEvent` 或 `replyReminder.type`）。
  - ⚠️ `hrReplyCount` / `lastCustReplyTimestamp` 是「該職缺 HR 對**所有**應徵者的回覆」統計
    （職缺回覆率），**不代表回覆我**——真實資料驗證：這兩欄 >0 但 `custReplyDate` 空時 104 仍只顯示
    「已讀」。**不可**納入 `derive_status`，否則會把只被已讀的投遞誤判成公司已回覆。
  - Phase 2 寫一個 `derive_status(item) -> str` 純函式集中此邏輯。

---

## Phase 2 待補（gaps）
1. ~~applications item 結構~~ ✅ 已用真實投遞確認（見上）；`status` 需 `derive_status` 推導。
2. **面試邀約精準判斷 + 日期**：`chatrooms` 列表只到 `lastEvent`；面試「日期」可能要開對話室或面試專屬端點。
3. **viewers 的 job_title 粒度**：`peruse-record/companies` 是公司層級；若要單一職缺粒度需另找端點。
4. **取數方式**：建議 Phase 2 用 `page.request.get(<api>)`（已登入 context 直接打 JSON）取代 DOM 解析。

## 對應 fixture（去識別化，供 Phase 2 解析 TDD）
- `tests/fixtures/viewers.json`、`tests/fixtures/messages.json`、`tests/fixtures/applications_empty.json`

## SP12 履歷讀取（2026-07-04 spike，capture_resume.py）
**結論：104 線上履歷是結構化、且登入態 XHR 讀得到** → SP12 可做真正的結構化比對/健檢。
- 履歷編輯頁：`pda.104.com.tw/profile/edit?vno=<vno>`（`my/resume/list` 會 302 轉到這、帶 vno）。
- **主端點**：`GET pda.104.com.tw/profile/ajax/resumeByBlock?vno=<vno>` → `{data, metadata}` 信封。
- 履歷清單（拿 vno/master）：`GET pda.104.com.tw/profile/ajax/completeResumeList?top=isMaster`。
- 其他：`profile/ajax/overview`、`inputField`、`options`、`resume-settings`、`api/user`。
- 我猜的 `/api/resume*` 直打端點全 404——履歷走 `profile/ajax/*` 而非 `/api/*`。
- **resumeByBlock.data 區塊**（每塊 `formData` 內）：
  info(基本資料)、education(educations[])、experience(experiences[]、seniority)、
  jobCondition(求職條件)、skill(skills[])、certificate、language、project(projects[])、
  portfolio、bio(自傳)、referrer；另有 progress(完成度%)、sidebar[](各塊 completed 旗標)。
- **PII 注意**：payload 含姓名/email/手機/地址/生日/身分證欄位——SP12 讀取後若送 LLM 是重個資出口，需審慎（captured/ 已 gitignore、FINDINGS 不記實值）。
