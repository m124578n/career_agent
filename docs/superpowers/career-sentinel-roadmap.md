# career-sentinel 路線圖 / Backlog

> 這是 career-sentinel（地端求職 agent）所有**未完成**需求與想法的單一收集處。
> 新點子、deferred 項目、技術債都記在這。每個子專案各自走 spec → plan → 實作。
> 最後更新：2026-07-03（SP9 完成）

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
- **SP6**：定期檢視提醒 + 桌面通知（serve 開著到 `notify_time` 提醒該檢視、桌面通知+儀表板橫幅、一鍵拉動態）。因 headful 限制採「到點提醒、一鍵執行」（排程器只設旗標不自爬）。新 `web/scheduler`(到點判斷純函式 + daemon thread + 記憶體狀態)、`GET /api/schedule`+`ack`、`run_pipeline` 回 `ChangeCounts`(拉完發「N 筆新動態」通知)、前端 `notify.ts`(Web Notification 未授權靜默 fallback)+controlled tab+儀表板橫幅。實測背景 thread 到點設 due。141 測試。
- **SP7**：行事曆整合（擷取 104 面試場次為第 4 類資料，併入既有 headful 登入態 scrape → 儀表板頂部「即將到來的面試」→ 每筆預填 Google 日曆連結、零 OAuth）。新 `scraper/interviews`(登入態打 `pda.104.com.tw/api/interviews`，`parse_interviews` 純函式壞筆略過、欄位 custName/jobName/interviewTime/address/jobUrl 映射，status 為無 legend 數字碼故存 raw、UI 不顯示 badge)、`calendar_link.build_gcal_link`(有時間→`dates=起/起+1h`、空/不可解析→不帶 dates fallback、全 urlencode)、store `interviews` table round-trip、`real.scrape` 加第 4 reader + `cli._carry_forward` 補第 4 欄位(**順手解掉「寫死三欄位」技術債**)、`GET /api/snapshot` 輸出 interviews+gcal_link(按 when 排序)、前端 Dashboard 區塊。面試**不進 diff/不進 SP6 通知**(新邀約已由 message `has_interview_invite` 粗略涵蓋)。最終全分支 review(opus) Ready to merge，零 Critical/Important。153 測試。**註：spec 原設計的 `thread_url`/status badge/開對話室 fallback，spike 實機確認後改為 `job_url`/「看職缺」+ 無 badge（payload 給 `chatroomId` 非 thread URL、status 無 legend）——刻意取代、非 regression。**

- **SP8**：整理助手（對話式履歷/需求整理）。聊天分頁：SSE 串流聊天（`llm.chat_stream` 兩 provider）、LLM 回覆結尾 `<suggestions>` JSON 由後端 `chat.StreamFilter` 截住解析成建議卡片一鍵套用（`apply_update` 9 項欄位白名單、失敗零部分寫入）、`op=remember` 自動寫入半永久 memory（唯一免確認路徑、只能進 MemoryState、側欄可刪、清空對話不清 memory）、對話 >30 則自動 compact 留 10 則（先 summary 成功才裁切、失敗不丟訊息）、中斷回覆不持久化。新增三張單列表（chat/preferences/memory，store 抽 `_load/_save_single` 共用 helper）。求職偏好檔案 `JobPreferences(locations/conditions/avoid)`。PII 界線：chat/memory 只進 LLM 對話（與 SP3 同級）、不進 digest/通知。最終全分支 review(opus) Ready to merge、零 Critical/Important。真機驗證回饋再收 7 項：聊天分頁 keepMounted 保留狀態（修切分頁紀錄消失）、expected_salary 契約改月薪語意（年薪自動換算）、平滑打字機（實測 provider 每 0.4s 給 ~10 字、SSE 無傳輸緩衝、WS 無益→前端佇列定速釋放）、助手訊息 Markdown 渲染（react-markdown+remark-gfm）、memory 自動維護（去重拒收+op=forget+🧹徽章）、memory LLM 整理 pass（>12 條回合尾端重整、失敗/空/變多不採用）、匯出求職檔案 MD（GET /api/export，帶去其他 LLM 平台續聊）。191 測試。

- **SP-UIUX**：前端整體改版（Cockpit 色系 × Exaggerated Minimalism 版面 × 左側欄）。theme.ts 逐字移植雲端 Cockpit（ink+tangerine/teal/amber/danger、Space Grotesk/IBM Plex）、AppShell 200px 側欄（全域重新抓取+設定移入、SP6 提醒橫幅升 App 層全域、聊天頁 display:none 恆掛載保串流）、六頁全部重整（儀表板大字級 KPI+扁平清單 hover 高亮、健檢雙欄診斷、比對大分數、JobRow 扁平列、聊天氣泡/徽章對齊）、Tabler SVG 全面替換 emoji icon。純前端、後端零 diff（reviewer 驗證）、191 測試不動。視覺方向經 visual companion 三方案 mockup 由使用者選定。最終全分支 review(opus) Ready to merge、零 Critical/Important（hover 高亮/a11y minor 當場修）。

- **SP9**：公司評價 web 研究。公司名旁 🔍 一鍵查→LLM 自帶 web search（**spike 實證 Foundry `web_search_20250305` 可用**、真實來源經交叉驗證；OpenAI 相容路徑走 OpenRouter `:online` 慣例、未測）→`research.py` provider-aware＋台灣站點優先 prompt→`CompanyResearch`（風險燈號白名單）→`company_research` KV 快取（TTL 7 天＋force）→`GET /api/research`→`ResearchButton` Modal（嵌儀表板四清單＋JobRow）。真機實測：精藤 37 秒查得 4 優點/5 缺點/8 真實來源（面試趣/比薪水/GoodJob）、快取命中 0.06 秒。安全：LLM 來源連結 scheme guard＋noopener（唯一新增的不可信 URL 面）。211 測試。

## 🔭 子專案（待做，建議順序）

| # | 子專案 | 內容 | 來源 |
|---|--------|------|------|
| ~~SP1~~ | ~~🖥️ 本地 Web 殼 + 儀表板~~ | ✅ 已完成（見上） | — |
| ~~SP2~~ | ~~⚙️ 設定 + 關注清單~~ | ✅ 已完成（見上） | — |
| ~~SP3~~ | ~~📋 履歷健檢~~ | ✅ 已完成（見上） | — |
| ~~SP4~~ | ~~🎯 JD × 履歷比對~~ | ✅ 已完成（見上） | — |
| ~~SP5~~ | ~~💡 工作推薦~~ | ✅ 已完成（見上） | — |
| ~~SP-Search~~ | ~~🔎 站內關鍵字職缺搜尋 + 比對~~ | ✅ 已完成（見上） | — |
| ~~SP6~~ | ~~⏰ 定期檢視 + 通知排程~~ | ✅ 已完成（見上） | — |
| ~~SP7~~ | ~~📅 行事曆整合~~ | ✅ 已完成（見上） | — |
| ~~SP8~~ | ~~💬 對話式履歷/需求整理~~ | ✅ 已完成（見上） | — |
| ~~SP9~~ | ~~🌐 公司評價 web 研究~~ | ✅ 已完成（見上） | — |
| **SP10** | 🔍 聊天中即時推職缺 | SP8 對話中 LLM 依偏好適時呼叫既有 SP-Search/推薦，聊天內帶出職缺卡片（需工具呼叫架構） | SP8 brainstorm 拆出（2026-07-02） |
| **SP11** | ✉️ 客製化履歷/求職信 + 投遞 + 追蹤 | 針對特定職缺客製化履歷與求職信→使用者逐筆確認後投遞→加追蹤清單。**投遞是高影響外部動作，104 投遞端點需先 spike、必須逐筆人工確認** | SP8 brainstorm 拆出（2026-07-02） |
| **SP12** | 📤 履歷回寫 104 | 本地整理好的履歷同步回 104 網站上的履歷。**登入態寫入操作、104 履歷編輯端點需先 spike、寫回前必須讓使用者確認 diff** | 使用者需求（2026-07-02） |

## 🔧 技術債 / 精修（穿插各 SP 或獨立小修）
- **SP9 review minors（皆 defer）**：sources 由 LLM 在最終 JSON 自報（可改從 `web_search_tool_result` 結構化 block 抽取更可靠）；同公司多列併發雙擊可能重複查（後端無鎖、單人可接受殘餘風險）；快取 key 未正規化（全形空白等變體會分裂快取）；三清單 ResearchButton 在 truncate Group 內（面試列在外、視覺不一致）；per-row idle Modal；`force` int 可改 bool；stale-cache 端點路徑無專測。
- **SP8 review minors（皆 defer、無阻塞）**：`chat_apply` 的 400 判斷耦合「不允許」訊息前綴（下次動 `apply_update` 時改結構化欄位如 `ApplyResult.code`）；無效非 remember 建議會成「套用必失敗」死卡片（可在 cards 過濾 ALLOWED 合法組合）；`readSse` 無終端 `dec.decode()` flush（理論多位元組尾字遺失）；`clearChat`/`deleteMemory` 未檢 `r.ok`（非 2xx 無聲成功）；SSE `error` 事件的 message 前端被丟只顯示固定「回覆中斷」；compact 在 `done` 前同步跑第二次 LLM 呼叫（spec 明訂接受、輸入鎖到結束）；中斷丟整輪含 user 訊息（spec 只要求丟回覆）；`keepMounted={false}` 串流中切分頁 setState on unmounted（console warning）；失敗卡片無重試；store `_load/_save_single` 無型別註記；`test_old_db_gains_new_tables` 未真模擬舊 schema DB。
- **全分頁**：目前每類只抓第 1 頁；需逐頁抓完整清單。
- **面試判斷精修**：目前「訊息含『面試』」啟發式可能誤判（婉拒信也提面試）；改用 `lastEvent.type` 對應或面試專屬端點。
- **應徵狀態細分**：目前只到 已送出/已讀/公司已回覆；想分 邀面試/婉拒（需跨訊息頁判斷）。
- ~~**`cli._carry_forward` 寫死三欄位**~~：✅ SP7 已補 interviews 第 4 欄位（`_carry_forward` 現顯式列全 4 類）。若未來再加第 5 類仍需手動補一行；徹底動態化（走 Snapshot 欄位反射）仍可做，但 4 類手寫清晰、暫不重構。
- **訊息跨 filter 去重**：`fetch_messages` 合併 exclusive+general 未以 `thread_id` 去重。
- **reader 名稱常數化**：`"viewers"/"applications"/"messages"` 散在 `real.scrape`/`_carry_forward`/警告字串，宜集中。
- **`parse_messages` 測試覆蓋**：未斷言 `raw` 與第二筆欄位；`parse_applications` 缺空清單測。
- **digest 個資外洩注意**：設了 `LLM_API_KEY` 時公司名/訊息會送外部 LLM——本地工具唯一的個資出口，未來上文件提醒。
- ~~**SP1 儀表板視覺對齊 Cockpit**~~：✅ SP-UIUX 完成（theme.ts 逐字移植＋六頁全面重整）。
- **SP-UIUX review minors（皆 defer）**：Dashboard/JobRow `key={i}`（既有 pattern）；completion effect dep 陣列已留註解；`@tabler/icons-react` 樹 npm audit 1 moderate+1 high（compile-time only、地端工具低風險，宜開 audit 追蹤）；KPI「新訊息」顯示總數非新增數（amber 後綴才是邀約數，文案語意可再斟酌）。
- **web runner 跨次共用 LLM digest**：`default_scrape` 走 `run_pipeline` 會算 digest（有 key 時打 LLM）但 web 用 `render_human`，該 digest 被丟棄；無 key 時無成本，有 key 時可改只存不彙整。
- **digest 彙整走 provider 層**：SP3 的 `llm` 已支援 Foundry，但 `digest.summarize` 仍只打 OpenAI 相容端點；Foundry 使用者的 LLM 每日彙整尚未啟用（走本地 `render_human`）。可把 digest 改用 `llm` 的 provider 分派（補一個 `llm.chat`）。
- **SP6 review minors**：`Dashboard.refresh()` 殘留空 `if (r.status !== "already_running") {}` dead code（純視覺噪音、行為正確，可刪只留 `setPolling(true)`）；桌面通知/橫幅的**真機 UI 目視**尚待使用者實跑（排程器背景邏輯已實測到點設 due，但通知彈窗+橫幅需瀏覽器目視確認）。
- **SP7 review minors（皆 defer、無阻塞）**：`_snapshot_payload` 排序 key `(iv.when=="", iv.when)` 對「非空但不可解析」的 `when`（如「待通知」）按 codepoint 排在有效日期間（顯示用、CJK 落在數字日期後、無害）——若要嚴格「無真日期→墊底」改成 key on `when` 是否可 parse；`Dashboard.tsx` 面試列 `key={i}` index key（唯讀整批重繪、低風險）；面試「加入 Google 日曆」Button 無空值 guard（`build_gcal_link` 永回非空 URL、目前無風險，僅 payload 契約變更時需注意）；`models.py` `Interview` 定義在 `Snapshot` 之後用 forward ref `"Interview"`（Pydantic v2 自動解析、153 測試過，但把被參照 model 定義在前可去除計畫自己標的脆弱性）；測試覆蓋 polish：`test_scrape_collects_all` 未斷言 `interviews==[]`、API 測試未鎖 keys 集合(status 缺席)/未測 no-data 空分支、`test_cli` 用 `str(Path)` 與 sibling `Path` 風格不一。
- **SP-Search review minors**：`SearchPage.run()`（及 `RecommendPage`/`MatchPage` 同款）缺 `try/finally`——`searchJobs`/`matchJob` 網路例外會卡住 loading spinner（既有跨分頁模板 pattern，值得統一補 `finally { setBusy(false) }`）；某些 104 職缺薪資顯示異常（真機見「月薪 196~395 元」）——`parse_recommendations._format_salary` 對 salaryLow/High 非典型值（單位/編碼異常職缺）無防護，推薦與搜尋共用，宜加合理性檢查或顯示原始。（最終 review 補記：`/api/search` 的 `store.load_settings` 在 try/except 外→settings 讀失敗會回 500 而非 502，可接受；`_conn()` sqlite 連線未顯式關閉是全 app 既有 pattern，宜全站統一收斂。）
- **SP5 review minors**：`MatchResult._clamp_score` 未捕 `OverflowError`（`float('inf')`→`int()` 溢位；JSON 無 infinity 故風險極低，一行加 `except` 即可）；`recommend._format_salary` 的 `salaryLow or 0` 對 0 冗贅（行為正確、純風格）；`RecommendPage` canMatch 首載閃爍（gate on `resume.isLoading`，同 MatchPage flicker）；「拉取推薦」loading 時按鈕動態文字被 spinner 遮；`getRecommend` 回 raw `Response` 與其他 getter 不一致（同 `matchJob` 模式，API 層重構時統一）。SP5 全分頁抓推薦（目前只第 1 頁，metadata.total 有 400 筆）。
- **SP4 review minors（SP5 前順手）**：`jobfetch.parse_job_detail` 的 specialty 加 `isinstance(s, dict)` 保護 + 濾空字串（SP5 跑多樣職缺更穩）；`MatchResult.score` clamp 0~100（避免 LLM 回 120 撐破 Progress 或非整數→500）；`match_job` 的 `RuntimeError→400` 改 typed exception；502 區分「抓取失敗 vs 解析失敗」；`MatchPage` 載入閃爍（gate on `isLoading`）。
- **SP3 review minors**：`resume_diagnose` 的 500 加 `logger.exception`（Foundry 是新整合、便於排錯）；no-key 改用 typed exception 而非裸 `RuntimeError`（避免深層 RuntimeError 被誤標 400）；`_foundry_parse_json` `max_tokens` 4096→8192（長診斷防截斷）；補測 OpenAI Bearer header + foundry kwargs；`ResumePage` 的 `setBusy` 加 try/finally、upload try/catch、useEffect 只 seed 一次（避免覆寫編輯中）。

## 💡 隨手記（未分類想法）
（之後想到的新點子先丟這）
- **媒合邏輯釐清 + 履歷關鍵字盤點（2026-07-01）**：目前 `match.py` 是**純 LLM 語意比對**（履歷全文 + JD → `MatchResult{score,reasons,gaps}`），非關鍵字字面比對——LLM 懂同義（Bicep≈Azure IaC、Synapse≈資料倉儲）。**軟性條件（公司文化/成長性）目前沒評**，屬 SP9（公司評價）。關鍵限制：**LLM 只看得到履歷裡寫出來的技能**，沒寫進去的就等於沒有。→ 待辦：對履歷做一次技能盤點（Bicep / Azure Synapse / Claude Code 等定位技能是否都「有出現」，措辭不必精準、有寫到即可），可直接用 **SP3 履歷健檢**針對目標職稱跑一次看「待補強」清單。
