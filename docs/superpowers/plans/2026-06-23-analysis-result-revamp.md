# 分析結果區改版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分析結果卡片可摺疊/展開、由 LLM 抽出職缺福利以 tag 呈現、候選清單可收合、「排序結果」正名「分析結果」。

**Architecture:** 後端在 `MatchAnalysis`/`JobMatch` 加 `benefits`，`_build_prompt` 讓 LLM 抽福利、`analyze` 透傳、`set_result` 寫入。前端 `MatchCard` 預設摺疊（摺疊頭部含分數+福利 tag），候選 panel 可收合。

**Tech Stack:** 後端 FastAPI + Pydantic（pytest + monkeypatch + mongomock_motor）；前端 React + Mantine + react-query + TypeScript（型別 gate `tsc --noEmit`）。

## Global Constraints

- 後端測試 pytest，async 直接 `async def`；LLM 用 `monkeypatch.setattr(llm, "parse", fake_parse)` stub；DB 用 `AsyncMongoMockClient()["test"]`
- 前端無單元測試框架；型別 gate `frontend/node_modules/.bin/tsc.cmd --noEmit`（exit 0）
- 前端 types/index.ts 與後端 schema 手動同步，欄位名一致（`benefits`）
- benefits：LLM 只抽 JD 明確提到的福利，標籤化、每項 ≤ 8 字、最多 6 項，沒提到留空
- 新欄位 optional/預設空，向後相容（舊 JobMatch 無 benefits → `[]`）
- 後端工作目錄 `backend/`，測試 `uv run pytest`
- commit 不加 `--no-verify`

---

### Task 1: 後端 schema + repository — benefits 欄位

**Files:**
- Modify: `backend/src/job_tracker/schemas/__init__.py`（`MatchAnalysis`、`JobMatch`）
- Modify: `backend/src/job_tracker/db/repositories.py`（`MatchRepository.set_result`）
- Test: `backend/tests/test_schemas.py`、`backend/tests/test_application_repository.py`（或新測試檔；放 schema 測試於 test_schemas）

**Interfaces:**
- Produces:
  - `MatchAnalysis.benefits: list[str]`（預設空）
  - `JobMatch.benefits: list[str]`（預設空）
  - `set_result` 寫入的 doc 含 `benefits`

- [ ] **Step 1: schema 失敗測試**

在 `test_schemas.py` 末尾加：

```python
def test_match_analysis_benefits_defaults_empty():
    from job_tracker.schemas import MatchAnalysis
    a = MatchAnalysis(score=80, reasons=[], gaps=[])
    assert a.benefits == []
    a2 = MatchAnalysis(score=80, reasons=[], gaps=[], benefits=["特休優於法令"])
    assert a2.benefits == ["特休優於法令"]


def test_jobmatch_benefits_defaults_empty():
    from job_tracker.schemas import Job, JobMatch
    job = Job(job_id="1", code="c1", title="t", company="co",
              url="https://www.104.com.tw/job/c1")
    m = JobMatch(job=job)
    assert m.benefits == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_schemas.py::test_match_analysis_benefits_defaults_empty -v`
Expected: FAIL — `TypeError`/`ValidationError`（benefits 未定義）

- [ ] **Step 3: schema 加欄位**

`schemas/__init__.py`，`MatchAnalysis` 內 `gaps` 後加：

```python
    benefits: list[str] = Field(
        default_factory=list, description="JD 明確提到的福利，標籤化（≤8字，最多6項）"
    )
```

`JobMatch` 內 `gaps` 後加：

```python
    benefits: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: repository 失敗測試**

在 `test_application_repository.py` 末尾加（檔頂已有 `AsyncMongoMockClient`、`MatchRepository` 之類 import；若無 `MatchRepository` 則加 `from job_tracker.db.repositories import MatchRepository`，並 import `Job, JobMatch, MatchAnalysis`）：

```python
async def test_set_result_writes_benefits():
    from job_tracker.db.repositories import MatchRepository
    from job_tracker.schemas import Job, JobMatch, MatchAnalysis
    from mongomock_motor import AsyncMongoMockClient

    db = AsyncMongoMockClient()["test"]
    mr = MatchRepository(db)
    job = Job(job_id="1", code="c1", title="t", company="co",
              url="https://www.104.com.tw/job/c1")
    await mr.set_match("s1", "u1", JobMatch(job=job, status="pending"))
    analysis = JobMatch(job=job, score=80, reasons=["r"], gaps=["g"],
                        benefits=["遠端一週三天"])
    await mr.set_result("s1", "1", analysis)
    got = await mr.get_match("s1", "1")
    assert got.benefits == ["遠端一週三天"]
    assert got.status == "done"
```

- [ ] **Step 5: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_application_repository.py::test_set_result_writes_benefits -v`
Expected: FAIL — `got.benefits == []`（set_result 未寫 benefits）

- [ ] **Step 6: repository 寫入 benefits**

`repositories.py` 的 `MatchRepository.set_result` 的 `$set` dict 加一行：

```python
                "benefits": analysis.benefits,
```

（放在 `"gaps": analysis.gaps,` 後面）

- [ ] **Step 7: 跑測試確認通過 + regression**

Run: `cd backend && uv run pytest -q`
Expected: 全部 PASS

- [ ] **Step 8: Commit**

```bash
git add backend/src/job_tracker/schemas/__init__.py backend/src/job_tracker/db/repositories.py backend/tests/test_schemas.py backend/tests/test_application_repository.py
git commit -m "feat(be): MatchAnalysis/JobMatch 加 benefits，set_result 寫入"
```

---

### Task 2: 後端 analyze + prompt — 抽福利並透傳

**Files:**
- Modify: `backend/src/job_tracker/services/job_matching.py`
- Test: `backend/tests/test_job_matching.py`

**Interfaces:**
- Consumes: Task 1 的 `MatchAnalysis.benefits`、`JobMatch.benefits`
- Produces: `analyze()` 回傳的 `JobMatch.benefits == analysis.benefits`；`_build_prompt` 內含抽福利指示

- [ ] **Step 1: 失敗測試（透傳 + prompt 指示）**

在 `test_job_matching.py` 末尾加：

```python
async def test_analyze_passes_benefits_through(monkeypatch):
    async def fake_parse(prompt, schema, **kwargs):
        # prompt 應包含抽福利的指示
        assert "福利" in prompt
        return MatchAnalysis(score=70, reasons=[], gaps=[],
                             benefits=["特休優於法令", "遠端一週三天"])

    monkeypatch.setattr(llm, "parse", fake_parse)
    m = await job_matching.analyze(make_target(), make_job(), make_detail())
    assert m.benefits == ["特休優於法令", "遠端一週三天"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_job_matching.py::test_analyze_passes_benefits_through -v`
Expected: FAIL — `assert "福利" in prompt`（prompt 尚無福利指示）或 `m.benefits` 不存在/為空

- [ ] **Step 3: prompt 加指示 + analyze 透傳**

`job_matching.py` 的 `_build_prompt`，把最後一行改成兩句：

```python
        "請評估契合度（0~100 分），並列出契合理由與待補強缺口。\n"
        "另外列出職缺 JD 中明確提到的福利（如特休、年終、遠端、彈性上班、股票等），"
        "每項標籤化、不超過 8 字、最多 6 項；JD 沒提到就不要列、不要臆測。"
```

`analyze()` 的 `return JobMatch(...)` 加 `benefits=analysis.benefits`：

```python
    return JobMatch(
        job=job,
        score=analysis.score,
        reasons=analysis.reasons,
        gaps=analysis.gaps,
        benefits=analysis.benefits,
        requires_external_apply=requires_external_apply(detail.description),
    )
```

- [ ] **Step 4: 跑測試確認通過 + regression**

Run: `cd backend && uv run pytest tests/test_job_matching.py -v && uv run pytest -q`
Expected: 全部 PASS（既有 `test_analyze_builds_jobmatch_from_llm` 等仍綠）

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/services/job_matching.py backend/tests/test_job_matching.py
git commit -m "feat(be): analyze 抽 JD 福利並透傳 benefits"
```

---

### Task 3: 前端 types — JobMatch.benefits

**Files:**
- Modify: `frontend/src/types/index.ts`（`JobMatch`）

**Interfaces:**
- Produces: `JobMatch.benefits: string[]`

- [ ] **Step 1: 加欄位**

`types/index.ts` 的 `interface JobMatch`，在 `gaps: string[];` 後加：

```typescript
  benefits: string[];
```

- [ ] **Step 2: 型別檢查**

Run: `cd frontend && ./node_modules/.bin/tsc.cmd --noEmit`
Expected: exit 0（既有用到 JobMatch 的地方因 benefits 非 optional 仍可編譯——皆由 API 回傳物件，不在前端手動建構 JobMatch）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(fe): JobMatch 型別加 benefits"
```

---

### Task 4: 前端 MatchCard — 摺疊/展開 + 福利 tag + 正名

**Files:**
- Modify: `frontend/src/pages/JobList.tsx`（`MatchCard` 與結果面板標題）

**Interfaces:**
- Consumes: Task 3 的 `JobMatch.benefits`
- Produces: `MatchCard` 預設摺疊，摺疊頭部顯示分數+福利 tag+展開鈕；展開顯示 meter/tags/chips/按鈕列

- [ ] **Step 1: 改 MatchCard return（摺疊結構 + 福利 tag）**

在 `MatchCard` 內，解構行加入 `benefits`：

```typescript
  const { job, score, reasons, gaps, requires_external_apply } = match;
  const benefits = match.benefits ?? [];
  const [expanded, setExpanded] = useState(false);
```

（`expanded` 宣告放在現有 `const [draft, setDraft] = useState(...)` 附近。）

把 `return ( ... )` 整段替換為：

```tsx
  return (
    <div className="jt-jobcard">
      <div className="jt-job-head">
        <div>
          <a className="jt-job-title" href={job.url} target="_blank" rel="noreferrer">
            {job.title}
          </a>
          <div className="jt-job-meta">
            {job.company}
            {job.salary ? ` · ${job.salary}` : ""}
          </div>
        </div>
        <div className="jt-score">
          <b>{score}</b>
          <small>match</small>
        </div>
      </div>

      {benefits.length > 0 && (
        <Group gap={6}>
          {benefits.map((b, i) => (
            <span key={`b${i}`} className="jt-chip"
                  style={{ color: "var(--jt-teal)", borderColor: "rgba(52,214,200,0.4)" }}>
              {b}
            </span>
          ))}
        </Group>
      )}

      {expanded && (
        <>
          <div className="jt-meter">
            <span style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
          </div>

          <div className="jt-tags">
            {reasons.map((r, i) => (
              <div key={`r${i}`} className="jt-tag" data-kind="pos">
                <span className="m">[+]</span>
                <span>{r}</span>
              </div>
            ))}
            {gaps.map((g, i) => (
              <div key={`g${i}`} className="jt-tag" data-kind="neg">
                <span className="m">[!]</span>
                <span>{g}</span>
              </div>
            ))}
          </div>

          {(requires_external_apply || hasLetter) && (
            <Group gap={8}>
              {requires_external_apply && (
                <span className="jt-chip">⚑ 需至官網投遞</span>
              )}
              {hasLetter && (
                <span className="jt-chip" style={{ color: "var(--jt-teal)", borderColor: "rgba(52,214,200,0.4)" }}>
                  ✎ 已寫求職信
                </span>
              )}
            </Group>
          )}
          <div style={{ borderTop: "1px solid var(--jt-border)", marginTop: 2 }} />
          <Group justify="flex-end" gap={8}>
            <Button
              size="xs"
              variant="light"
              color="teal"
              disabled={tracked || trackMut.isPending}
              loading={trackMut.isPending}
              onClick={() => trackMut.mutate()}
            >
              {tracked ? "✓ 已在追蹤清單" : "☆ 加入追蹤"}
            </Button>
            <Button size="xs" variant="default" onClick={openLetter}>
              {hasLetter ? "查看求職信" : "生成求職信"}
            </Button>
          </Group>
        </>
      )}

      <Group justify="center" mt={2}>
        <Button size="xs" variant="subtle" color="gray"
                onClick={() => setExpanded((e) => !e)}>
          {expanded ? "▴ 收合" : "▾ 展開"}
        </Button>
      </Group>

      <Modal
        opened={opened}
        onClose={close}
        size="lg"
        closeOnClickOutside={!letterMut.isPending}
        closeOnEscape={!letterMut.isPending}
        title={
          <span className="jt-eyebrow">
            求職信 // {job.company} · {job.title}
          </span>
        }
      >
```

（Modal 內容與結尾 `</Modal></div>` 維持原本不動——只替換到 `<Modal ...>` 開頭為止。注意替換後 Modal 仍在 `<div className="jt-jobcard">` 內。）

- [ ] **Step 2: 結果面板正名**

找到結果面板標題：

```tsx
                排序結果 // RANKED
```

改為：

```tsx
                分析結果 // RANKED
```

- [ ] **Step 3: 型別檢查**

Run: `cd frontend && ./node_modules/.bin/tsc.cmd --noEmit`
Expected: exit 0

- [ ] **Step 4: 手動驗證（後端與前端 dev server 已在跑）**

- 分析一筆職缺後，結果卡片**預設摺疊**：只見標題/公司/分數/福利 tag（若有）/「▾ 展開」
- 點「▾ 展開」→ 出現 meter、reasons/gaps、chips、加入追蹤/生成求職信按鈕；鈕變「▴ 收合」
- 面板標題顯示「分析結果 // RANKED」

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/JobList.tsx
git commit -m "feat(fe): 分析卡片摺疊/展開 + 福利 tag + 正名分析結果"
```

---

### Task 5: 前端 候選清單收合

**Files:**
- Modify: `frontend/src/pages/JobList.tsx`（候選 panel）

**Interfaces:**
- Produces: 候選 panel-head 有收合切換；收合時不渲染候選 panel-body

- [ ] **Step 1: 加收合 state**

在 `JobList` 元件，於 `const [resultLimit, setResultLimit] = useState(12);` 後加：

```typescript
  const [candOpen, setCandOpen] = useState(true);
```

- [ ] **Step 2: 候選 panel-head 加收合鈕 + body 條件渲染**

找到候選 panel 的 head：

```tsx
              <div className="jt-panel-head">
                <span className="jt-eyebrow">候選 // CANDIDATES · {candidates.length}</span>
                <Group gap={8}>
                  <Button size="xs" variant="default" onClick={() => crawlMut.mutate()}
                          disabled={busy} loading={crawlMut.isPending}>爬下一頁</Button>
                  <Button size="xs" color="tangerine"
                          disabled={pickedCandidates.length === 0 || analyzeMut.isPending}
                          loading={analyzeMut.isPending}
                          onClick={() => analyzeMut.mutate()}>
                    分析選中（{pickedCandidates.length}）
                  </Button>
                </Group>
              </div>
```

把 head 內的 `<Group gap={8}>` 改成在最前面加一顆收合鈕：

```tsx
              <div className="jt-panel-head">
                <span className="jt-eyebrow">候選 // CANDIDATES · {candidates.length}</span>
                <Group gap={8}>
                  <Button size="xs" variant="subtle" color="gray"
                          onClick={() => setCandOpen((o) => !o)}>
                    {candOpen ? "▾ 收合" : "▸ 展開"}
                  </Button>
                  <Button size="xs" variant="default" onClick={() => crawlMut.mutate()}
                          disabled={busy} loading={crawlMut.isPending}>爬下一頁</Button>
                  <Button size="xs" color="tangerine"
                          disabled={pickedCandidates.length === 0 || analyzeMut.isPending}
                          loading={analyzeMut.isPending}
                          onClick={() => analyzeMut.mutate()}>
                    分析選中（{pickedCandidates.length}）
                  </Button>
                </Group>
              </div>
```

把候選 panel-body 包進 `candOpen &&`。找到：

```tsx
              <div
                className="jt-panel-body"
                style={{ maxHeight: "55vh", overflowY: "auto" }}
              >
                <Stack gap={8}>
```

改為（在 body div 外包條件）：

```tsx
              {candOpen && (
              <div
                className="jt-panel-body"
                style={{ maxHeight: "55vh", overflowY: "auto" }}
              >
                <Stack gap={8}>
```

並在對應的候選 body 收尾 `</Stack>\n              </div>`（候選清單 map 結束處）補上 `)`：

```tsx
                </Stack>
              </div>
              )}
```

（注意：只包候選那一個 panel-body，不要動到結果面板的 panel-body。候選 body 的辨識點是它內含全選 `<Group>` 與 `candidates.map`。）

- [ ] **Step 3: 型別檢查**

Run: `cd frontend && ./node_modules/.bin/tsc.cmd --noEmit`
Expected: exit 0

- [ ] **Step 4: 手動驗證**

- 候選清單 head 出現「▾ 收合」；點擊後候選列表（含全選列）隱藏，head 的爬下一頁/分析選中仍在、鈕變「▸ 展開」
- 再點「▸ 展開」候選列表回來

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/JobList.tsx
git commit -m "feat(fe): 候選清單可收合"
```

---

## Self-Review 註記

- **Spec coverage**：benefits schema(T1)、prompt+透傳(T2)、set_result(T1)、types(T3)、
  摺疊+福利tag+正名(T4)、候選收合(T5) 皆有對應任務。
- **型別一致**：`benefits` 後端 `list[str]`／前端 `string[]`，欄位名一致；`MatchAnalysis`
  與 `JobMatch` 皆有 benefits；`analyze` 透傳 `analysis.benefits`。
- **摺疊預設**：T4 `useState(false)` = 預設摺疊，符合 spec。
- **相容**：T1 benefits 預設空、前端 `match.benefits ?? []`，舊資料安全。
- **候選收合範圍**：T5 只包候選 panel-body（辨識點：全選列 + candidates.map），不影響
  結果面板。
