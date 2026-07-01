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
- **SP5**：工作推薦（拉 104 個人化推薦清單→標 ★關注→逐筆手動比對，重用 SP4）。新 `scraper/recommend`(登入態抓 `personal-recommend-jobs`，需帶 `Referer` + www host Cloudflare clearance；薪資 `s10` 編碼解析)、`GET /api/recommend`(is_watched 標記/409/502/stateless)、前端「推薦」分頁(逐列獨立比對)。順手收 SP4 兩個 minor(score clamp、specialty 防禦)。真機驗證(抓到 20 筆真實推薦、薪資格式化正確)。114 測試。
- **SP-Search**：站內關鍵字職缺搜尋（輸入關鍵字→curl_cffi 打 104 **公開**搜尋 API→列出→逐筆比對）。新 `scraper/search`(`fetch_search` curl_cffi 公開端點不需登入 + `parse_search` 委派 `parse_recommendations`——搜尋結果結構與推薦完全相同)、`GET /api/search?kw=`(is_watched/400/502/stateless)、前端抽共用 `JobRow` 元件 + 「職缺搜尋」分頁(帶入關注詞、Enter 觸發)。真機驗證(搜「Python 後端」抓 22 筆真實職缺)。122 測試。一站式「找工作→比對」閉環成形。

## 🔭 子專案（待做，建議順序）

| # | 子專案 | 內容 | 來源 |
|---|--------|------|------|
| ~~SP1~~ | ~~🖥️ 本地 Web 殼 + 儀表板~~ | ✅ 已完成（見上） | — |
| ~~SP2~~ | ~~⚙️ 設定 + 關注清單~~ | ✅ 已完成（見上） | — |
| ~~SP3~~ | ~~📋 履歷健檢~~ | ✅ 已完成（見上） | — |
| ~~SP4~~ | ~~🎯 JD × 履歷比對~~ | ✅ 已完成（見上） | — |
| ~~SP5~~ | ~~💡 工作推薦~~ | ✅ 已完成（見上） | — |
| ~~SP-Search~~ | ~~🔎 站內關鍵字職缺搜尋 + 比對~~ | ✅ 已完成（見上） | — |
| **SP6** | ⏰ 定期檢視 + 通知排程 | 到點提醒（headful 限制→不自動爬）+ 桌面通知 + 一鍵拉動態。**spec + plan 已寫好、擱置待執行** | 新 + 舊「每日自動排程」 |
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
- **SP-Search review minors**：`SearchPage.run()`（及 `RecommendPage`/`MatchPage` 同款）缺 `try/finally`——`searchJobs`/`matchJob` 網路例外會卡住 loading spinner（既有跨分頁模板 pattern，值得統一補 `finally { setBusy(false) }`）；某些 104 職缺薪資顯示異常（真機見「月薪 196~395 元」）——`parse_recommendations._format_salary` 對 salaryLow/High 非典型值（單位/編碼異常職缺）無防護，推薦與搜尋共用，宜加合理性檢查或顯示原始。（最終 review 補記：`/api/search` 的 `store.load_settings` 在 try/except 外→settings 讀失敗會回 500 而非 502，可接受；`_conn()` sqlite 連線未顯式關閉是全 app 既有 pattern，宜全站統一收斂。）
- **SP5 review minors**：`MatchResult._clamp_score` 未捕 `OverflowError`（`float('inf')`→`int()` 溢位；JSON 無 infinity 故風險極低，一行加 `except` 即可）；`recommend._format_salary` 的 `salaryLow or 0` 對 0 冗贅（行為正確、純風格）；`RecommendPage` canMatch 首載閃爍（gate on `resume.isLoading`，同 MatchPage flicker）；「拉取推薦」loading 時按鈕動態文字被 spinner 遮；`getRecommend` 回 raw `Response` 與其他 getter 不一致（同 `matchJob` 模式，API 層重構時統一）。SP5 全分頁抓推薦（目前只第 1 頁，metadata.total 有 400 筆）。
- **SP4 review minors（SP5 前順手）**：`jobfetch.parse_job_detail` 的 specialty 加 `isinstance(s, dict)` 保護 + 濾空字串（SP5 跑多樣職缺更穩）；`MatchResult.score` clamp 0~100（避免 LLM 回 120 撐破 Progress 或非整數→500）；`match_job` 的 `RuntimeError→400` 改 typed exception；502 區分「抓取失敗 vs 解析失敗」；`MatchPage` 載入閃爍（gate on `isLoading`）。
- **SP3 review minors**：`resume_diagnose` 的 500 加 `logger.exception`（Foundry 是新整合、便於排錯）；no-key 改用 typed exception 而非裸 `RuntimeError`（避免深層 RuntimeError 被誤標 400）；`_foundry_parse_json` `max_tokens` 4096→8192（長診斷防截斷）；補測 OpenAI Bearer header + foundry kwargs；`ResumePage` 的 `setBusy` 加 try/finally、upload try/catch、useEffect 只 seed 一次（避免覆寫編輯中）。

## 💡 隨手記（未分類想法）
（之後想到的新點子先丟這）
- **媒合邏輯釐清 + 履歷關鍵字盤點（2026-07-01）**：目前 `match.py` 是**純 LLM 語意比對**（履歷全文 + JD → `MatchResult{score,reasons,gaps}`），非關鍵字字面比對——LLM 懂同義（Bicep≈Azure IaC、Synapse≈資料倉儲）。**軟性條件（公司文化/成長性）目前沒評**，屬 SP9（公司評價）。關鍵限制：**LLM 只看得到履歷裡寫出來的技能**，沒寫進去的就等於沒有。→ 待辦：對履歷做一次技能盤點（Bicep / Azure Synapse / Claude Code 等定位技能是否都「有出現」，措辭不必精準、有寫到即可），可直接用 **SP3 履歷健檢**針對目標職稱跑一次看「待補強」清單。
