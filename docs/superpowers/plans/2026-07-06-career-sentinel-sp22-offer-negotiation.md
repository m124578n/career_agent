# SP22：offer 談判建議 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 加 `negotiate_offer` 結構化 LLM 分析（web search 查台灣行情＋你其他 offer 當槓桿），經 `POST /api/negotiate {code}` 暴露，並在 offer 比較表按鈕與聊天提議卡兩處觸發。

**Architecture:** 比照公司研究（`research`）的 web-search LLM 樣式——抽共用 `research.web_search_complete` provider 分派，`negotiate.py` 用它產出結構化 `NegotiationAdvice`。端點組裝該 offer＋管道裡其他 offer（競品）＋期望薪資。前端比照 ResearchButton（Modal）＋比照 #5 tailor（聊天提議卡），兩者共用一個 NegotiationView 呈現元件。

**Tech Stack:** Python（LLM+web search，provider 分派）；React 18 + Mantine 7 + TanStack Query。

## Global Constraints

- **成本點了才跑**：negotiate 只在按「談判建議」時呼叫 /api/negotiate 才產生 LLM＋web search 成本；agent 只丟提議卡、不自行寫策略、不宣稱完成；工具迴圈無 negotiate。
- **只對 offer**：`/api/negotiate` 對非 offer 態或無 offer_json 的 code 回 400；聊天合約要求只對 offer 職缺提議。
- **競品槓桿**：把使用者其他 offer-state 職缺（排除自己）當競品餵進 prompt；期望薪資納入。
- **DRY**：web-search provider 分派抽 `research.web_search_complete` 共用，research 行為不變（既有 test_research.py 維持綠）。
- **重用、v1 不快取、不改 apply_update/ALLOWED**（negotiate 不走 chat/apply）；重用 `ResearchSource` 與 ResearchButton 的來源安全渲染慣例（`^https?://`）。
- 時間戳 `datetime.now().isoformat(timespec="seconds")`；後端綁 127.0.0.1。
- **測試指令（後端）**：於 `sentinel/` 用 `./.venv/Scripts/python.exe -m pytest -q`。
- **測試指令（前端）**：於 `sentinel/web/frontend/` 用 `npm run build`。

---

## File Structure

- `sentinel/src/career_sentinel/models.py` — `NegotiationAdvice`（Task 1）。
- `sentinel/src/career_sentinel/research.py` — 抽 `web_search_complete`（Task 1）。
- `sentinel/src/career_sentinel/negotiate.py` — 新模組（Task 1）。
- `sentinel/src/career_sentinel/web/app.py` — `POST /api/negotiate`（Task 2）。
- `sentinel/src/career_sentinel/chat.py` — `_CONTRACT` 加 negotiate 提議（Task 3）。
- `sentinel/web/frontend/src/api.ts` — 型別＋negotiateOffer（Task 4）。
- `sentinel/web/frontend/src/NegotiateButton.tsx` — 新（含 export NegotiationView）（Task 4）。
- `sentinel/web/frontend/src/Dashboard.tsx` — offer 表加按鈕（Task 4）。
- `sentinel/web/frontend/src/ChatPage.tsx` — NegotiateCard＋分派（Task 5）。
- 測試：`test_negotiate.py`（Task 1）、`test_web_negotiate.py`（Task 2）、`test_chat_apply.py`/`test_chat_tools.py`（Task 3）。

---

### Task 1: NegotiationAdvice 模型 ＋ 共用 web_search_complete ＋ negotiate.py

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`、`sentinel/src/career_sentinel/research.py`
- Create: `sentinel/src/career_sentinel/negotiate.py`
- Test: `sentinel/tests/test_negotiate.py`

**Interfaces:**
- Produces:
  - `models.NegotiationAdvice`（summary/market_assessment/leverage_points/suggested_ask/scripts/risks/sources: list[ResearchSource]/advised_at）。
  - `research.web_search_complete(prompt: str, *, feature: str, client=None) -> str`。
  - `negotiate.build_negotiate_prompt(offer, company, title, other_offers, expected_salary) -> str`。
  - `negotiate.negotiate_offer(offer: OfferDetail, company: str, title: str, other_offers: list[dict], expected_salary: int | None, *, client=None, feature="談判建議") -> NegotiationAdvice`。

- [ ] **Step 1: 寫失敗測試**

新建 `sentinel/tests/test_negotiate.py`：

```python
import pytest

from career_sentinel import negotiate, research
from career_sentinel.models import NegotiationAdvice, OfferDetail


def test_web_search_complete_dispatch(monkeypatch):
    monkeypatch.setattr(research, "_foundry_research", lambda p, c, f: "FOUNDRY")
    monkeypatch.setattr(research, "_openai_research", lambda p, c, f: "OPENAI")
    monkeypatch.setattr(research, "llm_provider", lambda: "foundry")
    assert research.web_search_complete("hi", feature="x") == "FOUNDRY"
    monkeypatch.setattr(research, "llm_provider", lambda: "openai")
    assert research.web_search_complete("hi", feature="x") == "OPENAI"
    monkeypatch.setattr(research, "llm_provider", lambda: "")
    with pytest.raises(RuntimeError):
        research.web_search_complete("hi", feature="x")


def test_build_negotiate_prompt_has_offer_and_competitors():
    p = negotiate.build_negotiate_prompt(
        OfferDetail(salary_year=1200000, location="台北"), "甲公司", "後端工程師",
        [{"company": "乙公司", "salary_year": 1400000}], 90000)
    assert "甲公司" in p and "後端工程師" in p and "1200000" in p
    assert "乙公司" in p and "1400000" in p   # 競品槓桿
    assert "90000" in p                        # 期望薪資
    assert "JSON" in p


def test_negotiate_offer_parses(monkeypatch):
    fake = ('{"summary":"可談","market_assessment":"低於行情","leverage_points":["有競品offer"],'
            '"suggested_ask":"開到140萬","scripts":["我另有一個 offer…"],"risks":["別太硬"],'
            '"sources":[{"title":"比薪水","url":"https://x"}]}')
    monkeypatch.setattr(research, "web_search_complete", lambda prompt, **k: fake)
    r = negotiate.negotiate_offer(OfferDetail(salary_year=1200000), "甲", "後端", [], 90000)
    assert isinstance(r, NegotiationAdvice)
    assert r.summary == "可談" and r.suggested_ask == "開到140萬"
    assert r.leverage_points == ["有競品offer"] and r.advised_at
    assert r.sources[0].url == "https://x"
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_negotiate.py -q`
Expected: FAIL（`negotiate` 模組不存在、`research.web_search_complete` 不存在）

- [ ] **Step 3: 加 `NegotiationAdvice`（`models.py`）**

在 `class CompanyResearch` 之後加（`ResearchSource` 已定義在前）：

```python
class NegotiationAdvice(BaseModel):
    summary: str = ""
    market_assessment: str = ""
    leverage_points: list[str] = Field(default_factory=list)
    suggested_ask: str = ""
    scripts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    advised_at: str = ""
```

- [ ] **Step 4: 抽 `web_search_complete`（`research.py`）**

在 `research_company` 之前加公開函式，並把 `research_company` 改為呼叫它：

```python
def web_search_complete(prompt: str, *, feature: str, client=None) -> str:
    """依 provider 跑一次帶 web search 的 LLM 補全，回文字。"""
    provider = llm_provider()
    if provider == "openai":
        return _openai_research(prompt, client, feature)
    if provider == "foundry":
        return _foundry_research(prompt, client, feature)
    raise RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")


def research_company(name: str, *, client=None, feature: str = "公司研究") -> CompanyResearch:
    prompt = build_research_prompt(name)
    text = web_search_complete(prompt, feature=feature, client=client)
    r = CompanyResearch.model_validate(json.loads(llm._extract_json(text)))
    r.company = name
    r.researched_at = datetime.now().isoformat(timespec="seconds")
    return r
```

- [ ] **Step 5: 建 `negotiate.py`**

新建 `sentinel/src/career_sentinel/negotiate.py`：

```python
"""SP22 offer 談判建議：LLM+web search 依 offer 明細與競品給議價策略與話術。"""
from __future__ import annotations

import json
from datetime import datetime

from . import llm, research
from .models import NegotiationAdvice, OfferDetail


def build_negotiate_prompt(offer: OfferDetail, company: str, title: str,
                           other_offers: list[dict], expected_salary: int | None) -> str:
    lines = [f"我拿到「{company}」的「{title}」offer，請幫我想議價策略與話術。", "", "這個 offer 條件："]
    if offer.salary_year is not None:
        lines.append(f"- 年薪：{offer.salary_year}")
    if offer.salary_month is not None:
        lines.append(f"- 月薪：{offer.salary_month}")
    if offer.location:
        lines.append(f"- 地點：{offer.location}")
    if offer.level:
        lines.append(f"- 職級：{offer.level}")
    if offer.start_date:
        lines.append(f"- 到職日：{offer.start_date}")
    if offer.notes:
        lines.append(f"- 備註：{offer.notes}")
    if expected_salary:
        lines.append(f"\n我的期望月薪：{expected_salary}")
    if other_offers:
        lines.append("\n我手上其他 offer（可當競品槓桿）：")
        for o in other_offers:
            parts = [o.get("company") or "（某公司）"]
            if o.get("salary_year") is not None:
                parts.append(f"年薪 {o['salary_year']}")
            elif o.get("salary_month") is not None:
                parts.append(f"月薪 {o['salary_month']}")
            lines.append("- " + "，".join(parts))
    lines += [
        "",
        "請用網路搜尋這個職位在台灣的市場薪資區間（可參考比薪水、104 薪資、Glassdoor、Dcard 等）。",
        "把我手上其他 offer 當作議價槓桿。只輸出單一 JSON 物件（不要 markdown 圍欄、不要其他文字），格式：",
        '{"summary": "一句話：能不能談、談多少", "market_assessment": "相對台灣市場行情的評估", '
        '"leverage_points": ["你的籌碼…"], "suggested_ask": "建議開多少或談什麼（薪資/簽約金/股票/到職日）", '
        '"scripts": ["可直接用的議價話術…"], "risks": ["風險/注意事項…"], '
        '"sources": [{"title": "來源標題", "url": "https://…"}]}',
        "規則：查不到市場行情時在 market_assessment 註明資料稀少，並仍基於競品 offer 與期望薪資給策略；"
        "sources 只列實際參考到的網頁。",
    ]
    return "\n".join(lines)


def negotiate_offer(offer: OfferDetail, company: str, title: str,
                    other_offers: list[dict], expected_salary: int | None,
                    *, client=None, feature: str = "談判建議") -> NegotiationAdvice:
    prompt = build_negotiate_prompt(offer, company, title, other_offers, expected_salary)
    text = research.web_search_complete(prompt, feature=feature, client=client)
    r = NegotiationAdvice.model_validate(json.loads(llm._extract_json(text)))
    r.advised_at = datetime.now().isoformat(timespec="seconds")
    return r
```

- [ ] **Step 6: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_negotiate.py -q`
Expected: PASS

- [ ] **Step 7: research 回歸（重構不得破壞）**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_research.py -q`
Expected: PASS（research_company 重構後行為不變）

- [ ] **Step 8: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠）

- [ ] **Step 9: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/research.py sentinel/src/career_sentinel/negotiate.py sentinel/tests/test_negotiate.py
git commit -m "feat(sentinel): NegotiationAdvice + negotiate_offer（web-search 議價建議）+ 抽 web_search_complete（SP22）"
```

---

### Task 2: `POST /api/negotiate` 端點

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_negotiate.py`

**Interfaces:**
- Consumes: Task 1 `negotiate.negotiate_offer`；`store.get_tracked_job`、`pipeline.build_pipeline`、`store.load_preferences`、`OfferDetail`（app.py 已 import pipeline/store/OfferDetail）。
- Produces: `POST /api/negotiate`（body `{code}`）→ `NegotiationAdvice` dict；非 offer/無明細/不存在 → 400。

- [ ] **Step 1: 寫失敗測試**

新建 `sentinel/tests/test_web_negotiate.py`：

```python
from fastapi.testclient import TestClient

from career_sentinel import negotiate as negmod, store
from career_sentinel.models import NegotiationAdvice, OfferDetail
from career_sentinel.web import app as webapp


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_negotiate_endpoint_offer(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite")
    conn = store.connect(db)
    store.set_tracked_state(conn, "of1", "offer", offer=OfferDetail(salary_year=1200000))
    store.set_tracked_state(conn, "of2", "offer", offer=OfferDetail(salary_year=1400000))
    from career_sentinel.models import JobPreferences
    store.save_preferences(conn, JobPreferences(expected_salary=90000))

    captured = {}
    def fake_neg(offer, company, title, other_offers, expected_salary, **kw):
        captured["others"] = other_offers
        captured["expected"] = expected_salary
        return NegotiationAdvice(summary="可談")
    monkeypatch.setattr(negmod, "negotiate_offer", fake_neg)

    c = TestClient(webapp.create_app(db_path=db))
    r = c.post("/api/negotiate", json={"code": "of1"})
    assert r.status_code == 200 and r.json()["summary"] == "可談"
    # 其他 offer（of2）當競品，期望薪資帶入
    assert any(o.get("salary_year") == 1400000 for o in captured["others"])
    assert captured["expected"] == 90000


def test_negotiate_non_offer_400(tmp_path):
    from career_sentinel.models import TrackedJob
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="m1", state="matched", match_score=70))
    r = _client(tmp_path).post("/api/negotiate", json={"code": "m1"})
    assert r.status_code == 400


def test_negotiate_missing_400(tmp_path):
    r = _client(tmp_path).post("/api/negotiate", json={"code": "nope"})
    assert r.status_code == 400
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_web_negotiate.py -q`
Expected: FAIL（端點 404）

- [ ] **Step 3: import negotiate（`app.py`）**

在 app.py 頂部 `from .. import ...`（含 pipeline/store 那行）加入 `negotiate`：

```python
from .. import calendar_link, chat as chatmod, company_link, config, diagnosis, diff, digest, jobfetch, llm, match, negotiate, pipeline, research, resume, store, tailor, usage as usagemod, watch
```

- [ ] **Step 4: 加端點（`app.py`）**

在 `/api/tailor` 或 `/api/apply/open` 附近加：

```python
    class _NegotiateReq(BaseModel):
        code: str

    @app.post("/api/negotiate")
    def negotiate_offer_ep(req: _NegotiateReq) -> dict:
        conn = _conn()
        tj = store.get_tracked_job(conn, req.code)
        if tj is None or tj.state != "offer" or not tj.offer_json:
            raise HTTPException(status_code=400, detail="此職缺沒有 offer 明細可談判")
        offer = OfferDetail.model_validate_json(tj.offer_json)
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

（`_NegotiateReq` 定義在函式內或與其他 `_*Req` 同區皆可；此處就近定義。`OfferDetail` 已在 app.py import。）

- [ ] **Step 5: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_web_negotiate.py -q`
Expected: PASS

- [ ] **Step 6: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠）

- [ ] **Step 7: Commit**

```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_negotiate.py
git commit -m "feat(sentinel): POST /api/negotiate（組 offer+競品+期望薪資→談判建議）（SP22）"
```

---

### Task 3: 聊天合約加 negotiate 提議

**Files:**
- Modify: `sentinel/src/career_sentinel/chat.py`
- Test: `sentinel/tests/test_chat_apply.py`、`sentinel/tests/test_chat_tools.py`

**Interfaces:**
- Produces: `_CONTRACT` 含 negotiate 提議；`build_system_prompt` 回傳含 `negotiate`。

- [ ] **Step 1: 寫失敗測試**

在 `sentinel/tests/test_chat_apply.py` 末尾加：

```python
def test_apply_update_rejects_negotiate(tmp_path):
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="negotiate", op="run", payload={"code": "x"}))
    assert not r.ok
```

在 `sentinel/tests/test_chat_tools.py` 末尾加：

```python
def test_system_prompt_mentions_negotiate():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState())
    assert "negotiate" in p
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_tools.py::test_system_prompt_mentions_negotiate -q`
Expected: FAIL（prompt 無 negotiate）

- [ ] **Step 3: `_CONTRACT` 加 negotiate 範例（`chat.py`）**

把 `_CONTRACT` 中 tailor 範例那行（結尾無逗號、後接 `]}</suggestions>`）：

```python
  {"field": "tailor", "op": "run", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師"}}
]}</suggestions>
```

改為（tailor 行補逗號、其後加 negotiate 範例行）：

```python
  {"field": "tailor", "op": "run", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師"}},
  {"field": "negotiate", "op": "run", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師"}}
]}</suggestions>
```

- [ ] **Step 4: `_CONTRACT` 加 negotiate 規則（`chat.py`）**

在既有 tailor 規則（結尾 `…只丟提議卡。`）之後、`- 沒有要更新時不要輸出 <suggestions> 區塊。` 之前，插入：

```python
- 談判建議（negotiate/run）：使用者想要某 **offer** 的議價策略與話術時，提議
  {"field": "negotiate", "op": "run", "payload": {"code": "...", "company": "...", "title": "..."}}。
  僅對已標記錄取（offer）的職缺；payload.code 必來自 get_pipeline 的實際 offer 職缺、不得杜撰。
  這是**提議**，等使用者按下才實際生成（花 LLM 錢＋web search）——**你不要自行寫議價策略或聲稱已完成**，只丟提議卡。
```

- [ ] **Step 5: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_apply.py tests/test_chat_tools.py -q`
Expected: PASS

- [ ] **Step 6: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠）

- [ ] **Step 7: Commit**

```bash
git add sentinel/src/career_sentinel/chat.py sentinel/tests/test_chat_apply.py sentinel/tests/test_chat_tools.py
git commit -m "feat(sentinel): 聊天合約加 negotiate 提議動作（offer 談判建議）（SP22）"
```

---

### Task 4: api.ts ＋ NegotiateButton ＋ offer 表按鈕（前端）

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`、`sentinel/web/frontend/src/Dashboard.tsx`
- Create: `sentinel/web/frontend/src/NegotiateButton.tsx`

**Interfaces:**
- Consumes: `POST /api/negotiate`（Task 2）。
- Produces: `NegotiationAdvice` 型別、`negotiateOffer(code)`、`NegotiateButton`、`NegotiationView`（供 Task 5 聊天卡重用）。

- [ ] **Step 1: api.ts 加型別與函式**

在 `ResearchSource`/`CompanyResearch` 型別附近加：

```ts
export interface NegotiationAdvice {
  summary: string;
  market_assessment: string;
  leverage_points: string[];
  suggested_ask: string;
  scripts: string[];
  risks: string[];
  sources: ResearchSource[];
  advised_at: string;
}

export async function negotiateOffer(code: string): Promise<Response> {
  return fetch("/api/negotiate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
}
```

- [ ] **Step 2: 建 `NegotiateButton.tsx`（含 export NegotiationView）**

新建 `sentinel/web/frontend/src/NegotiateButton.tsx`：

```tsx
import { ActionIcon, Anchor, Button, Group, List, Loader, Modal, Stack, Text } from "@mantine/core";
import { IconMoneybag } from "@tabler/icons-react";
import { useState } from "react";
import { negotiateOffer, type NegotiationAdvice } from "./api";

export function NegotiationView({ data }: { data: NegotiationAdvice }) {
  return (
    <Stack gap="sm">
      {data.summary && <Text size="sm" fw={600} style={{ lineHeight: 1.7 }}>{data.summary}</Text>}
      {data.market_assessment && (
        <div>
          <Text size="sm" fw={600} mb={2}>市場評估</Text>
          <Text size="sm" c="dark.1">{data.market_assessment}</Text>
        </div>
      )}
      {data.leverage_points.length > 0 && (
        <div>
          <Text size="sm" fw={600} c="teal.5" mb={2}>你的籌碼</Text>
          <List size="sm" spacing={2}>{data.leverage_points.map((p, i) => <List.Item key={i}>{p}</List.Item>)}</List>
        </div>
      )}
      {data.suggested_ask && (
        <div>
          <Text size="sm" fw={600} mb={2}>建議開價</Text>
          <Text size="sm" c="dark.1">{data.suggested_ask}</Text>
        </div>
      )}
      {data.scripts.length > 0 && (
        <div>
          <Text size="sm" fw={600} mb={2}>議價話術</Text>
          <List size="sm" spacing={4}>{data.scripts.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
        </div>
      )}
      {data.risks.length > 0 && (
        <div>
          <Text size="sm" fw={600} c="amber.5" mb={2}>風險</Text>
          <List size="sm" spacing={2}>{data.risks.map((r, i) => <List.Item key={i}>{r}</List.Item>)}</List>
        </div>
      )}
      {data.sources.length > 0 && (
        <div>
          <Text size="sm" fw={600} mb={2}>來源</Text>
          <Stack gap={2}>
            {data.sources.map((s, i) => {
              const safe = /^https?:\/\//i.test(s.url) ? s.url : undefined;
              return safe
                ? <Anchor key={i} href={safe} target="_blank" rel="noopener noreferrer" size="xs">{s.title || s.url}</Anchor>
                : <Text key={i} size="xs" c="dimmed">{s.title || s.url}</Text>;
            })}
          </Stack>
        </div>
      )}
    </Stack>
  );
}

export default function NegotiateButton({ code, company }: { code: string; company?: string; title?: string }) {
  const [opened, setOpened] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [data, setData] = useState<NegotiationAdvice | null>(null);

  async function load() {
    setErr(null); setBusy(true);
    try {
      const r = await negotiateOffer(code);
      const body = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(body.detail ?? "產生失敗"); return; }
      setData(body as NegotiationAdvice);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  }

  function open() { setOpened(true); if (!data && !busy) load(); }

  return (
    <>
      <ActionIcon variant="subtle" color="gray" size="xs" title="談判建議"
        style={{ flexShrink: 0 }} onClick={open}>
        <IconMoneybag size={13} />
      </ActionIcon>
      <Modal opened={opened} onClose={() => setOpened(false)} size="lg"
        title={`談判建議：${company ?? ""}`}>
        {busy && (
          <Group justify="center" py="xl">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">分析議價策略中（約 20–60 秒）…</Text>
          </Group>
        )}
        {err && !busy && (
          <Stack align="flex-start">
            <Text c="danger.6" size="sm">{err}</Text>
            <Button size="compact-sm" variant="light" onClick={load}>重試</Button>
          </Stack>
        )}
        {data && !busy && (
          <Stack gap="sm">
            <NegotiationView data={data} />
            <Group justify="space-between" mt="xs">
              <Text size="xs" c="dimmed">產於 {data.advised_at}</Text>
              <Button size="compact-xs" variant="subtle" onClick={load}>重新產生</Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </>
  );
}
```

- [ ] **Step 3: offer 比較表加 NegotiateButton（`Dashboard.tsx`）**

`Dashboard.tsx` import 加：

```tsx
import NegotiateButton from "./NegotiateButton";
```

把 offer 比較表的「公司·職稱」儲存格（現為）：

```tsx
                        <Table.Td>
                          <Text size="sm" fw={600}>{j.company}</Text>
                          <Text size="xs" c="dimmed">{j.title}</Text>
                        </Table.Td>
```

改為（加談判建議按鈕，stopPropagation 避免觸發 openCard）：

```tsx
                        <Table.Td>
                          <Group gap={6} wrap="nowrap">
                            <div style={{ minWidth: 0 }}>
                              <Text size="sm" fw={600}>{j.company}</Text>
                              <Text size="xs" c="dimmed">{j.title}</Text>
                            </div>
                            <span onClick={(e) => e.stopPropagation()}>
                              <NegotiateButton code={j.code} company={j.company} title={j.title} />
                            </span>
                          </Group>
                        </Table.Td>
```

- [ ] **Step 4: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 成功（`tsc -b && vite build` 無型別/未用 import 錯誤）

- [ ] **Step 5: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/NegotiateButton.tsx sentinel/web/frontend/src/Dashboard.tsx
git commit -m "feat(sentinel): 談判建議 api + NegotiateButton + offer 比較表按鈕（SP22）"
```

---

### Task 5: 聊天 NegotiateCard（前端）

**Files:**
- Modify: `sentinel/web/frontend/src/ChatPage.tsx`

**Interfaces:**
- Consumes: Task 4 `negotiateOffer`、`NegotiationView`、`NegotiationAdvice`；`field=="negotiate"` 的建議。

- [ ] **Step 1: 補 import（`ChatPage.tsx`）**

`./api` import 加 `negotiateOffer, type NegotiationAdvice`；並 import `NegotiationView`：

```tsx
import {
  applyUpdate, clearChat, deleteMemory, getChat, getResume, getSnapshot, negotiateOffer, openApplyPage,
  readSse, sendChat, SuggestedUpdate, tailorApplication, uploadResume,
  type NegotiationAdvice, type RecommendedJob, type TailoredApplication,
} from "./api";
import { NegotiationView } from "./NegotiateButton";
```

- [ ] **Step 2: 加 `NegotiateCard` 元件（`ChatPage.tsx`，在 TailorCard 之後）**

```tsx
function NegotiateCard({ payload }: { payload: { code: string; company?: string; title?: string } }) {
  const [result, setResult] = useState<NegotiationAdvice | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setErr(null); setBusy(true);
    try {
      const r = await negotiateOffer(payload.code);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "產生失敗"); return; }
      setResult(b as NegotiationAdvice);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  };

  return (
    <Paper bg="dark.6" radius="md" px="md" py="sm" maw="92%">
      <Group justify="space-between" wrap="nowrap" mb={result ? "sm" : 0}>
        <Text size="sm"><b>談判建議</b> {payload.company ?? ""}{payload.title ? ` · ${payload.title}` : ""}</Text>
        {!result && <Button size="compact-xs" loading={busy} onClick={run}>談判建議</Button>}
      </Group>
      {err && <Text size="xs" c="danger.6">{err}</Text>}
      {result && <NegotiationView data={result} />}
    </Paper>
  );
}
```

- [ ] **Step 3: 建議渲染分派加 negotiate（`ChatPage.tsx`）**

把既有分派：

```tsx
                {m.suggestions?.map((s, j) =>
                  s.field === "tailor"
                    ? <TailorCard key={j} payload={(s.payload ?? {}) as { code: string; company?: string; title?: string }} />
                    : <SuggestionCard key={j} s={s} />
                )}
```

改為：

```tsx
                {m.suggestions?.map((s, j) =>
                  s.field === "tailor"
                    ? <TailorCard key={j} payload={(s.payload ?? {}) as { code: string; company?: string; title?: string }} />
                    : s.field === "negotiate"
                      ? <NegotiateCard key={j} payload={(s.payload ?? {}) as { code: string; company?: string; title?: string }} />
                      : <SuggestionCard key={j} s={s} />
                )}
```

- [ ] **Step 4: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 成功（無型別/未用 import 錯誤）

- [ ] **Step 5: Commit**

```bash
git add sentinel/web/frontend/src/ChatPage.tsx
git commit -m "feat(sentinel): 聊天 NegotiateCard——按鈕跑談判建議（SP22）"
```

---

## Self-Review

**Spec coverage：**
- NegotiationAdvice 模型 → Task 1 ✅
- web_search_complete 抽共用（DRY，research 不回歸）→ Task 1 ✅
- negotiate.py（build_negotiate_prompt 含競品/期望、negotiate_offer 解析）→ Task 1 ✅
- POST /api/negotiate（組 offer+競品+期望，非 offer→400）→ Task 2 ✅
- 聊天合約加 negotiate 提議（只對 offer、不走 apply_update）→ Task 3 ✅
- api.ts + NegotiateButton(Modal) + offer 表按鈕 → Task 4 ✅
- 聊天 NegotiateCard（重用 NegotiationView）→ Task 5 ✅
- Global Constraints（點了才跑、只對 offer、競品槓桿、DRY、v1 不快取、不改 apply_update）各 Task 遵守 ✅

**Placeholder scan：** 無 TBD/TODO；每步含完整程式碼與確切指令。（Task 2 Step 1 的佔位測試已在同步驟以完整版取代並註明。）

**Type consistency：** `NegotiationAdvice`（summary/market_assessment/leverage_points/suggested_ask/scripts/risks/sources/advised_at）於 models/api.ts/NegotiationView 一致；`negotiate_offer(offer, company, title, other_offers, expected_salary)` 於 negotiate/app/測試一致；`web_search_complete(prompt, *, feature, client)` 於 research/negotiate/測試一致；`negotiateOffer(code)`、`negotiate` 提議 field 於前後端一致；`NegotiationView` 由 NegotiateButton export、ChatPage import 重用。
