# career-sentinel 路線圖 / Backlog

> 這是 career-sentinel（地端求職 agent）所有**未完成**需求與想法的單一收集處。
> 新點子、deferred 項目、技術債都記在這。每個子專案各自走 spec → plan → 實作。
> 最後更新：2026-06-28

## ✅ 已完成
- **Phase 1**：管線骨架（config/models/store/diff/digest/browser/cli + 假爬蟲），30 測試。
- **Phase 2**：三個真 104 爬蟲（誰看過我/應徵/訊息），`run` 讀真實資料、比對、彙整、容錯。真機驗證通過。
- 過 Cloudflare：rebrowser-playwright headful；login 用純 Chrome。端點記在 `sentinel/spike/FINDINGS.md`。
- **SP1**：本地 web 殼 + 儀表板（`career-sentinel serve`，FastAPI + React/Mantine）；三面板 + 彙整 + 網頁「重新抓取」觸發 headful 爬取 + 輪詢更新。62 測試、真機端到端驗證通過。
- **SP2**：設定 + 關注清單（設定頁存關注公司/關鍵字/通知時間 + 儀表板命中即時標 ★關注）。`watch.is_watched` 純函式供 SP5 重用；通知時間先存(SP6 發)。77 測試、真機驗證通過。
- **SP3**：履歷健檢（上傳 PDF/txt→針對目標職位 LLM 產出優勢/待補強）。新 `llm.parse_json` **provider-aware**(OpenAI 相容 + Azure Foundry/Anthropic)、`config.llm_provider` 偵測、前端 Tabs(儀表板/履歷健檢)。真機用 Azure Foundry/Claude 驗證高品質診斷。90 測試。
- **SP4**：JD × 履歷比對（貼 104 職缺網址→curl_cffi 抓 JD→對履歷算吻合度+缺技能）。`jobfetch`(104 公開詳情)+`match`(重用 llm.parse_json) 供 SP5 重用；前端「JD 比對」分頁。真機驗證(PHP 職缺給 Python 履歷正確判語言不符)。102 測試。

## 🔭 子專案（待做，建議順序）

| # | 子專案 | 內容 | 來源 |
|---|--------|------|------|
| ~~SP1~~ | ~~🖥️ 本地 Web 殼 + 儀表板~~ | ✅ 已完成（見上） | — |
| ~~SP2~~ | ~~⚙️ 設定 + 關注清單~~ | ✅ 已完成（見上） | — |
| ~~SP3~~ | ~~📋 履歷健檢~~ | ✅ 已完成（見上） | — |
| ~~SP4~~ | ~~🎯 JD × 履歷比對~~ | ✅ 已完成（見上） | — |
| **SP5** | 💡 工作推薦 | 104 推薦端點 `api/jobs/personal-recommend-jobs` + 關注過濾 + SP4 排序 | 新 |
| **SP6** | ⏰ 定期檢視 + 通知排程 | 按設定時間自動跑（爬+比對+推薦）、符合條件通知 | 新 + 舊「每日自動排程」 |
| **SP7** | 📅 行事曆整合 | 面試**確切日期**擷取（需開對話室/面試端點）+ 自動進 Google Calendar | 舊 deferred |
| **SP8** | 💬 對話式履歷/需求整理 | 聊天介面邊聊邊整理履歷與求職偏好（需即時串流 UI） | 舊 deferred（原始願景） |
| **SP9** | 🌐 公司評價 web 研究 | 自動上網查公司評價並彙整 | 舊 deferred（原始願景） |

## 🔧 技術債 / 精修（穿插各 SP 或獨立小修）
- **全分頁**：目前每類只抓第 1 頁；需逐頁抓完整清單。
- **面試判斷精修**：目前「訊息含『面試』」啟發式可能誤判（婉拒信也提面試）；改用 `lastEvent.type` 對應或面試專屬端點。
- **應徵狀態細分**：目前只到 已送出/已讀/公司已回覆；想分 邀面試/婉拒（需跨訊息頁判斷）。
- **`cli._carry_forward` 寫死三欄位**：未來加第 4 類會漏；改為動態走 Snapshot 欄位。
- **訊息跨 filter 去重**：`fetch_messages` 合併 exclusive+general 未以 `thread_id` 去重。
- **reader 名稱常數化**：`"viewers"/"applications"/"messages"` 散在 `real.scrape`/`_carry_forward`/警告字串，宜集中。
- **`parse_messages` 測試覆蓋**：未斷言 `raw` 與第二筆欄位；`parse_applications` 缺空清單測。
- **digest 個資外洩注意**：設了 `LLM_API_KEY` 時公司名/訊息會送外部 LLM——本地工具唯一的個資出口，未來上文件提醒。
- **SP1 儀表板視覺對齊 Cockpit**：SP1 先用 Mantine 預設深色主題；之後複製雲端 `theme.ts`/`.jt-*`、tangerine/teal 雙訊號色做主題 polish。
- **web runner 跨次共用 LLM digest**：`default_scrape` 走 `run_pipeline` 會算 digest（有 key 時打 LLM）但 web 用 `render_human`，該 digest 被丟棄；無 key 時無成本，有 key 時可改只存不彙整。
- **digest 彙整走 provider 層**：SP3 的 `llm` 已支援 Foundry，但 `digest.summarize` 仍只打 OpenAI 相容端點；Foundry 使用者的 LLM 每日彙整尚未啟用（走本地 `render_human`）。可把 digest 改用 `llm` 的 provider 分派（補一個 `llm.chat`）。
- **SP4 review minors（SP5 前順手）**：`jobfetch.parse_job_detail` 的 specialty 加 `isinstance(s, dict)` 保護 + 濾空字串（SP5 跑多樣職缺更穩）；`MatchResult.score` clamp 0~100（避免 LLM 回 120 撐破 Progress 或非整數→500）；`match_job` 的 `RuntimeError→400` 改 typed exception；502 區分「抓取失敗 vs 解析失敗」；`MatchPage` 載入閃爍（gate on `isLoading`）。
- **SP3 review minors**：`resume_diagnose` 的 500 加 `logger.exception`（Foundry 是新整合、便於排錯）；no-key 改用 typed exception 而非裸 `RuntimeError`（避免深層 RuntimeError 被誤標 400）；`_foundry_parse_json` `max_tokens` 4096→8192（長診斷防截斷）；補測 OpenAI Bearer header + foundry kwargs；`ResumePage` 的 `setBusy` 加 try/finally、upload try/catch、useEffect 只 seed 一次（避免覆寫編輯中）。

## 💡 隨手記（未分類想法）
（之後想到的新點子先丟這）
