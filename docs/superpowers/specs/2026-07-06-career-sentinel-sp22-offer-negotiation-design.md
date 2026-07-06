# SP22：offer 談判建議 設計

**日期：** 2026-07-06
**狀態：** 設計定案，待實作

## 這是什麼

career-sentinel 求職流水線的加值子專案：吃 SP20 存下的 offer 明細（`OfferDetail`）＋你手上**其他的 offer（競品槓桿）**＋期望薪資，用 LLM＋web search 查台灣市場行情，給**議價策略與話術**。放兩處觸發：**offer 比較表按鈕**（比照公司研究 ResearchButton）＋**聊天提議卡**（比照 #5 tailor）。屬 LLM 花錢動作，**點了才跑**。

## 目標

一句話：**加 `negotiate_offer` 結構化 LLM 分析（web search 查行情＋你其他 offer 當槓桿），經 `POST /api/negotiate {code}` 暴露，並在 offer 比較表按鈕與聊天提議卡兩處觸發。**

## 現況（實作依據）

- **`OfferDetail`（models.py）**：salary_year/salary_month/location/level/start_date/notes。存於 `TrackedJob.offer_json`（SP20）；`PipelineJob.offer`（pipeline 帶出）。
- **`research.py`**：web-search LLM 樣式——`research_company(name) -> CompanyResearch`；provider 分派 `_openai_research(prompt, client, feature)`（OpenRouter `model:online`）、`_foundry_research(prompt, client, feature)`（`web_search_20250305` tool）；`llm._extract_json` 解析。`ResearchSource`（title/url）既有可重用。
- **`match.py`/`tailor.py`/`diagnosis.py`**：純 prompt builder＋LLM，web 層以參數傳入。
- **Dashboard offer 比較表（SP20）**：`offerJobs = pipe.filter(state==="offer")`，Mantine `Table` 每列一個 offer（公司·職稱/年薪/月薪/地點/職級/到職日/分數/備註），點列 `openCard`。
- **`ResearchButton.tsx`**：Modal，開啟時載入、busy/err/data、force 重查。
- **聊天 `<suggestions>` 提議卡（#5）**：`{"field":"tailor","op":"run","payload":{...}}` → 前端分派 TailorCard 按鈕跑 `/api/tailor`。`chat.py _CONTRACT` 列動作規則。
- **`store.load_preferences(conn).expected_salary`**（期望月薪）；`pipeline.build_pipeline(conn)`（拿所有 offer-state job 當競品）。

## 資料模型（models.py）

```python
class NegotiationAdvice(BaseModel):
    summary: str = ""            # 一句話：能不能談、談多少
    market_assessment: str = ""  # 這個 offer 相對台灣市場行情
    leverage_points: list[str] = Field(default_factory=list)   # 你的籌碼（競品 offer、稀缺技能…）
    suggested_ask: str = ""      # 建議開多少/談什麼（薪資、簽約金、股票、到職日…）
    scripts: list[str] = Field(default_factory=list)           # 可直接用的議價話術
    risks: list[str] = Field(default_factory=list)             # 風險/注意事項
    sources: list[ResearchSource] = Field(default_factory=list)  # web search 來源（重用 ResearchSource）
    advised_at: str = ""         # ISO
```

## 後端變更

### 1. 共用 web-search helper（`research.py`，DRY）

把 `research_company` 的 provider 分派抽成公開函式，research 與 negotiate 共用（避免重複 openai/foundry 管線）：

```python
def web_search_complete(prompt: str, *, feature: str, client=None) -> str:
    """依 provider 跑一次帶 web search 的 LLM 補全，回文字。"""
    provider = llm_provider()
    if provider == "openai":
        return _openai_research(prompt, client, feature)
    if provider == "foundry":
        return _foundry_research(prompt, client, feature)
    raise RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")
```

`research_company` 改為呼叫 `web_search_complete(prompt, feature=feature, client=client)`（行為不變，既有 research 測試須維持綠）。

### 2. `negotiate.py`（新模組）

```python
def build_negotiate_prompt(offer, company, title, other_offers, expected_salary) -> str: ...
def negotiate_offer(offer: OfferDetail, company: str, title: str,
                    other_offers: list[dict], expected_salary: int | None,
                    *, client=None, feature: str = "談判建議") -> NegotiationAdvice:
    prompt = build_negotiate_prompt(offer, company, title, other_offers, expected_salary)
    text = research.web_search_complete(prompt, feature=feature, client=client)
    r = NegotiationAdvice.model_validate(json.loads(llm._extract_json(text)))
    r.advised_at = datetime.now().isoformat(timespec="seconds")
    return r
```

- `build_negotiate_prompt`：把這個 offer（company/title/年薪/月薪/地點/職級/到職日/備註）、**其他 offer 清單（競品，含公司與薪資）**、期望月薪組進 prompt；指示：用 web search 查該職位在台灣的市場薪資區間；**明確把競品 offer 當議價槓桿**；輸出單一 JSON（NegotiationAdvice 欄位，無 markdown 圍欄）；查不到行情時在 market_assessment 註明並仍給基於競品/期望的策略。`other_offers` 每筆 `{company, title, salary_year, salary_month}`。

### 3. `POST /api/negotiate`（web/app.py）

```python
class _NegotiateReq(BaseModel):
    code: str

@app.post("/api/negotiate")
def negotiate(req: _NegotiateReq) -> dict:
    conn = _conn()
    tj = store.get_tracked_job(conn, req.code)
    if tj is None or tj.state != "offer" or not tj.offer_json:
        raise HTTPException(status_code=400, detail="此職缺沒有 offer 明細可談判")
    offer = OfferDetail.model_validate_json(tj.offer_json)
    # 其他 offer 當競品槓桿（排除自己）
    others = []
    for pj in pipeline.build_pipeline(conn):
        if pj.state == "offer" and pj.code != req.code and pj.offer is not None:
            others.append({"company": pj.company, "title": pj.title,
                           "salary_year": pj.offer.salary_year, "salary_month": pj.offer.salary_month})
    expected = store.load_preferences(conn).expected_salary
    try:
        result = negotiate.negotiate_offer(offer, tj.company, tj.title, others, expected)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="產生談判建議失敗，請重試")
    return result.model_dump()
```

- import `negotiate`、`OfferDetail`（app.py 已 import pipeline/store/OfferDetail）。
- **v1 不快取**（每次點重跑；offer 少、刻意觸發）。

### 4. 聊天合約加 negotiate 提議（`chat.py _CONTRACT`）

- 範例加：`{"field": "negotiate", "op": "run", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師"}}`。
- 規則補述：`negotiate`＝提議「幫這個 **offer** 想議價策略與話術」。**僅對已標記錄取（offer）的職缺**；payload.code 來自 get_pipeline 的實際 offer 職缺、不得杜撰；這是**提議**，等使用者按下才實際跑（花 LLM 錢＋web search）；agent 不自行寫策略、不宣稱已完成。
- **不改 `apply_update`/`ALLOWED`**（negotiate 由前端直接打 /api/negotiate，比照 tailor）。

## 前端變更

### 5. api.ts

- `NegotiationAdvice` 型別（對應後端）。
- `negotiateOffer(code: string): Promise<Response>`（`POST /api/negotiate`，body `{code}`）。

### 6. `NegotiateButton.tsx`（新，比照 ResearchButton）

- props：`{ code: string; company?: string; title?: string }`。
- ActionIcon/Button「談判建議」→ Modal；開啟時 `negotiateOffer(code)`；busy（「分析議價策略中（約 20–60 秒）…」）/err（重試）/data。
- data 渲染：summary、market_assessment、leverage_points（籌碼）、suggested_ask（建議開價）、scripts（話術，逐條）、risks（風險）、sources（連結，比照 ResearchButton 的 `^https?://` 安全檢查）。「重新產生」按鈕重跑。

### 7. offer 比較表加按鈕（`Dashboard.tsx`）

- offer 比較表每列「公司·職稱」儲存格加 `<NegotiateButton code={j.code} company={j.company} title={j.title} />`；用 `<span onClick={(e)=>e.stopPropagation()}>` 包住避免觸發 `openCard`（比照既有 ResearchButton 包法）。

### 8. 聊天 NegotiateCard（`ChatPage.tsx`）

- 建議渲染分派加：`s.field === "negotiate"` → `<NegotiateCard payload=... />`（比照 tailor 分派）。
- `NegotiateCard`：顯示「談判建議【company · title】」＋按鈕；按下 `negotiateOffer(code)` → 渲染 NegotiationAdvice（同 NegotiateButton 的呈現，可抽共用呈現片段或各自渲染）；r.ok 錯誤處理。

## Global Constraints（實作時必守）

- **成本點了才跑**：negotiate 只在按「談判建議」（表格按鈕或聊天卡按鈕）時呼叫 /api/negotiate 才產生 LLM＋web search 成本；agent 只丟提議卡、不自行寫策略、不宣稱完成；工具迴圈無 negotiate（不自動跑）。
- **只對 offer**：`/api/negotiate` 對非 offer 態或無 offer_json 的 code 回 400；聊天合約要求只對 offer 職缺提議。
- **競品槓桿**：把使用者其他 offer-state 職缺（排除自己）當競品餵進 prompt；期望薪資納入。
- **DRY**：web-search provider 分派抽 `research.web_search_complete` 共用，research 行為不變（既有測試維持綠）。
- **重用、v1 不快取、不改 apply_update/ALLOWED**（negotiate 不走 chat/apply）；重用 `ResearchSource`、ResearchButton 的來源安全渲染慣例。
- **相容**：`NegotiationAdvice`/negotiate 工具/卡片皆加法；既有 research/match/tailor、SSE、卡片、offer 比較表其餘欄位不變。
- 時間戳 `datetime.now().isoformat(timespec="seconds")`；後端綁 `127.0.0.1`；前端 `npm run build` 必過。

## 測試策略

- **`research.web_search_complete`**（mock `_openai_research`/`_foundry_research`）：依 provider 分派；無 provider → RuntimeError。既有 `research_company` 測試維持綠（重構後行為不變）。
- **`build_negotiate_prompt`**（純函式）：含 offer 欄位、其他 offer（競品）與期望薪資的文字；要求 JSON 輸出。
- **`negotiate_offer`**（mock `research.web_search_complete` 回一段 JSON）：解析成 `NegotiationAdvice`、`advised_at` 有值；壞 JSON → 由呼叫端 500（web 層測）。
- **`POST /api/negotiate`**（mock `negotiate.negotiate_offer`）：
  - offer-state job（有 offer_json）→ 200、回 advice；競品其他 offer 有被組進 `other_offers`（用一個會捕捉參數的 fake 驗證 others 含另一筆 offer）。
  - 非 offer 態 / 無 offer_json / code 不存在 → 400。
  - negotiate_offer 拋 RuntimeError → 400；其他 Exception → 500。
- **聊天合約**：`build_system_prompt` 含 `negotiate`；`apply_update` 對 field="negotiate" → ok=False（不誤收）。
- **前端**：無單元測試，靠 `npm run build` ＋人工（表格按鈕開 Modal 跑建議、聊天 negotiate 卡）。

## 明確不做（Out of Scope）

- 快取談判建議（v1 每次重跑）、多幣別/稅後試算、股票/獎金結構化估值。
- 自動談判、代發議價信、代填 104。
- 對非 offer 態職缺給建議。
- 既有 UI/UX 其他精修。
