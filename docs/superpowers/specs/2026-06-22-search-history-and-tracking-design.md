# 分析歷史紀錄 ＋ 求職追蹤清單 — 設計

日期：2026-06-22
狀態：已核可，待實作

## 目標

1. **分析歷史**：把「每次爬取並分析」保留成一筆可回顧的歷史紀錄，不再用 destructive clear 把舊結果（含已寫求職信）刪掉。可在歷史之間切換、可在舊歷史上繼續操作、可手動刪除單筆。
2. **追蹤清單**：使用者可把職缺加入求職追蹤清單，以五欄看板管理投遞與面試進度。入口在求職信生成完成後。

## 範圍切分

- **本次 spec**
  - 分析歷史（search runs）：建立／列表／切換／續抓下一批／刪除
  - 追蹤清單核心：加入／看板列表／改狀態／移除
  - 銜接：求職信 modal 內「加入追蹤」鈕
- **下個 sub-project（不在本次）**
  - 面試多輪時間軸、面試筆記
  - 看板拖拉 UI
  - 本次先保留 `events` 資料骨架與「下拉改狀態」，供下次擴充

## 決策摘要

| 主題 | 決策 |
|---|---|
| 一筆歷史的邊界 | 每次新搜尋＝一筆；「分析下一批」append 到同一筆 |
| 回顧舊歷史 | 可繼續操作（續抓下一批、生成／查看求職信） |
| 歷史累積控管 | 可手動刪除單筆，無自動上限 |
| 資料模型 | 方案 A：`searches` collection ＋ `matches` 綁 `search_id` |
| 加入追蹤的方式 | 手動「加入追蹤」鈕（生成求職信不等於投遞） |
| 追蹤狀態 | 五欄看板：待投遞 → 已投遞 → 面試中 → Offer → 結束 |

## 資料模型

新增／改造 3 個 collection。

```
searches
  { _id, user, keyword, target, created_at, next_offset, count }
  - target 為當次 ResumeTarget 的快照（履歷／目標日後會變，歷史須凍結當時條件，
    且續抓下一批要沿用當時 keyword/target 才一致）
  - next_offset：已分析到第幾筆，供「下一批」起點
  - count：結果筆數（顯示用）

matches
  { _id: "{search_id}|{job_id}", search_id, user, job_id,
    score, reasons, gaps, requires_external_apply, job, cover_letter? }
  - _id 由 user|job_id 改為 search_id|job_id：同一職缺在不同 search 各自獨立一筆
    （不同次分析／目標，分數與求職信本就應獨立）
  - 求職信仍存於 match 上，沿用「按 key 更新單筆」

applications
  { _id: "{user}|{job_id}", user, job_id, job, source_search_id,
    cover_letter?, status, created_at, updated_at, events: [ {ts, type, note} ] }
  - 以 user|job_id 去重：同一職缺即使出現在多筆 search，追蹤清單只一筆
  - job、cover_letter 為加入當下的快照：即使日後刪掉來源 search 或爬蟲快取過期，
    追蹤清單仍完整
  - status ∈ {to_apply, applied, interviewing, offer, closed}
  - events：時間軸骨架，本次只在改狀態時 append 一筆 {ts, type:"status", note}
```

## API

前綴 `/api`，皆需登入（沿用現有 `current_user`）。

### 分析歷史

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/jobs/searches` | body `{keyword, target}`；建立 search、分析第一批、回傳 `{search_id, matches}`。受每日額度限制。 |
| POST | `/jobs/searches/{id}/next` | 用 search 上的 keyword/target/next_offset 續抓下一批；更新 next_offset/count。受額度限制。 |
| GET | `/jobs/searches` | 該 user 歷史列表（僅 metadata，created_at desc） |
| GET | `/jobs/searches/{id}/matches` | 該 search 的排序結果 |
| DELETE | `/jobs/searches/{id}` | 刪除 search 及其 matches（cascade） |
| POST | `/jobs/searches/{id}/cover-letter` | body `{job_id}`；定位該 search 的 match，生成並存求職信 |

`POST /jobs/searches` 與 `/next` 以實際分析筆數計入 `daily_usage`（沿用現有 quota 行為）。

### 追蹤清單

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/applications` | body `{search_id, job_id}`；從對應 match 取 job＋cover_letter 快照加入，status=`to_apply`；若已存在則回現有（不重複建立） |
| GET | `/applications` | 該 user 全部 applications（看板用） |
| PATCH | `/applications/{job_id}` | body `{status}`；更新狀態並 append 一筆 status event；更新 updated_at |
| DELETE | `/applications/{job_id}` | 移除 |

加入追蹤／改狀態不呼叫 LLM、不計額度。

## 前端

### JobList 頁
- 結果區上方一列**歷史 chips**：「{keyword} · {建立時間} · {count} 筆」，點選載入該 search 的 matches，選中高亮，各 chip 可刪除。
- 「爬取並分析」→ `POST /jobs/searches`（開新歷史並設為選中）。
- 「分析下一批」→ `POST /jobs/searches/{選中id}/next`（在當前選中 search 上續抓）。
- MatchCard 求職信 modal：生成完成後多一顆「加入追蹤」鈕；已加入顯示「✓ 已在追蹤清單」（停用）。

### 追蹤清單頁 `/applications`（看板）
- 五欄：待投遞 / 已投遞 / 面試中 / Offer / 結束，對應五個 status。
- 卡片顯示：公司 · 職缺 · 分數 · 求職信入口。
- 改狀態：MVP 用下拉（或左右移動鈕）；拖拉留下個 sub-project。
- 導覽列新增入口。

視覺細節（chips 樣式、看板配色）沿用現有 Cockpit 暗色主題，實作時微調。

## 遷移

單人 dev 階段，現有 `matches`（舊 `user|job_id` 結構）與其求職信**直接清掉重來**，不寫遷移腳本。上線前資料可丟。

## 測試（TDD）

- `SearchRepository`：create／list（desc）／get／更新 next_offset／delete cascade（連帶刪 matches）
- `MatchRepository`（改造）：set／list by search_id（排序）／set_cover_letter by search_id+job_id
- `ApplicationRepository`：add（去重，重複加同職缺仍一筆）／list／set_status（append event、更新 updated_at）／remove
- API：searches 各端點、cover-letter 定位正確、applications 各端點、加入追蹤不影響 quota
- 既有測試：移除／改寫依賴舊 `matches` 扁平結構與 `/jobs/analyze`、`MatchRepository.clear` 的測試

## 影響到的既有程式碼

- `backend/src/job_tracker/db/repositories.py`：`MatchRepository` 改 key、移除 `clear`；新增 `SearchRepository`、`ApplicationRepository`
- `backend/src/job_tracker/api/routers/jobs.py`：`/analyze` 改為 `/searches`＋`/next`；新增歷史 CRUD 與 cover-letter；新增 `routers/applications.py`
- `backend/src/job_tracker/services/analyze.py`：`analyze_jobs` 改為以 search 為單位寫入（帶 search_id）
- `backend/src/job_tracker/api/deps.py`：新增 `get_search_repo`、`get_application_repo`
- `frontend/src/pages/JobList.tsx`：歷史 chips、改打新端點、加入追蹤鈕
- `frontend/src/api/client.ts`、`types.ts`：新增 searches／applications 型別與呼叫
- 新增 `frontend/src/pages/Applications.tsx` 與路由、導覽入口
