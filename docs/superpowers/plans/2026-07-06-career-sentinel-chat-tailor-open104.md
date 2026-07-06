# 聊天客製化＋連 104（#5）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 agent 在聊天提議 `tailor` 動作卡，使用者按下後前端直接呼叫既有 `/api/tailor` 產出客製化建議＋求職信並渲染在聊天，附「開 104 投遞頁」按鈕（既有 `/api/apply/open`）。

**Architecture:** 重用既有 `/api/tailor`、`/api/apply/open`（零新後端端點）。後端只在 `chat.py` `_CONTRACT` 加 `tailor` 提議說明讓 agent 會丟提議；前端把 `field=="tailor"` 的建議渲染成新的 TailorCard（按下才跑 tailor、成本在按下時），結果附開 104 投遞頁按鈕。

**Tech Stack:** Python（chat prompt 合約）；React 18 + Mantine 7 + TanStack Query。

## Global Constraints

- **成本把關**：tailor 只在使用者按下「客製化」時才跑；agent 只丟提議卡、不自行生成客製化內容、不宣稱已完成。
- **agent 不寫入 104**：「開 104 投遞頁」只呼叫既有 `/api/apply/open`（登入態 Chrome 開頁），使用者親手投遞；不代填代送。
- **重用、零新後端端點**：直接用既有 `/api/tailor`、`/api/apply/open`；**不改 `apply_update`/`ALLOWED`**（tailor 不走 chat/apply）。
- **需履歷**：未上傳履歷時 /api/tailor 回 400，TailorCard 顯示該訊息（不崩）。
- **相容**：`tailor` 為新的建議 field，前端分派新增、既有 SuggestionCard（prefs/管道動作/memory）行為不變；`SuggestedUpdate.payload` 已在（SP21），後端 SSE 骨架不動。
- **測試指令（後端）**：於 `sentinel/` 用 `./.venv/Scripts/python.exe -m pytest -q`（預設 shell python 缺 pytest，勿用）。
- **測試指令（前端）**：於 `sentinel/web/frontend/` 用 `npm run build`。

---

## File Structure

- `sentinel/src/career_sentinel/chat.py` — `_CONTRACT` 加 tailor 提議範例與規則（Task 1）。
- `sentinel/tests/test_chat_apply.py` — parse_suggestions 解析 tailor、apply_update 拒收 tailor（Task 1）。
- `sentinel/tests/test_chat_tools.py` — build_system_prompt 含 tailor（Task 1）。
- `sentinel/web/frontend/src/ChatPage.tsx` — TailorCard 元件 ＋ 建議渲染分派（Task 2）。

---

### Task 1: `_CONTRACT` 加 tailor 提議（後端）

**Files:**
- Modify: `sentinel/src/career_sentinel/chat.py`
- Test: `sentinel/tests/test_chat_apply.py`、`sentinel/tests/test_chat_tools.py`

**Interfaces:**
- Produces: `chat._CONTRACT` 含 `tailor`/`run` 提議範例與規則；`build_system_prompt(...)` 回傳（含 _CONTRACT）內含 `tailor`。
- 既有 `parse_suggestions`（解析 `<suggestions>`）與 `apply_update`（不含 tailor→fallback ok=False）行為驗證。

- [ ] **Step 1: 寫失敗測試（parse + apply reject，`test_chat_apply.py`）**

在 `sentinel/tests/test_chat_apply.py` 末尾加：

```python
def test_parse_suggestions_tailor():
    tail = ('<suggestions>{"items":[{"field":"tailor","op":"run",'
            '"payload":{"code":"abc12","company":"甲","title":"後端"}}]}</suggestions>')
    items = chat.parse_suggestions(tail)
    assert len(items) == 1
    assert items[0].field == "tailor" and items[0].op == "run"
    assert items[0].payload["code"] == "abc12" and items[0].payload["title"] == "後端"


def test_apply_update_rejects_tailor(tmp_path):
    # tailor 不走 apply_update（前端直接打 /api/tailor）；誤打到 apply 應落 fallback ok=False
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="tailor", op="run", payload={"code": "x"}))
    assert not r.ok
```

- [ ] **Step 2: 寫失敗測試（prompt 含 tailor，`test_chat_tools.py`）**

在 `sentinel/tests/test_chat_tools.py` 末尾加：

```python
def test_system_prompt_mentions_tailor():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState())
    assert "tailor" in p
```

- [ ] **Step 3: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_apply.py tests/test_chat_tools.py -q`
Expected: FAIL（`test_system_prompt_mentions_tailor` 失敗——prompt 尚無 tailor；parse/apply 兩測可能已過，屬正常，重點是 prompt 測試失敗驅動實作）

- [ ] **Step 4: `_CONTRACT` 加 tailor 範例（`chat.py`）**

把 `_CONTRACT` 中 untrack 範例那行（結尾無逗號、後接 `]}</suggestions>`）：

```python
  {"field": "untrack", "op": "set", "payload": {"code": "abc12", "company": "台積電"}}
]}</suggestions>
```

改為（untrack 行補逗號、其後加 tailor 範例行）：

```python
  {"field": "untrack", "op": "set", "payload": {"code": "abc12", "company": "台積電"}},
  {"field": "tailor", "op": "run", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師"}}
]}</suggestions>
```

- [ ] **Step 5: `_CONTRACT` 加 tailor 規則（`chat.py`）**

在管道動作規則那條（結尾 `...**不要在回覆中聲稱已完成**。`）之後、`- 沒有要更新時不要輸出 <suggestions> 區塊。` 之前，插入一條 tailor 規則：

```python
  實際結果，**不得杜撰**。這些動作只是「提議」，會等使用者按下確認才生效——**不要在回覆中聲稱已完成**。
- 客製化（tailor/run）：使用者想要某職缺的客製化履歷與求職信時，提議
  {"field": "tailor", "op": "run", "payload": {"code": "...", "company": "...", "title": "..."}}。
  需使用者已上傳履歷；payload.code 必來自 get_pipeline/search_jobs/get_job_detail 的實際結果、不得杜撰。
  這是**提議**，會等使用者按下「客製化」才實際生成（花 LLM 錢）——**你不要自行寫出客製化內容或聲稱已完成**，只丟提議卡。
- 沒有要更新時不要輸出 <suggestions> 區塊。
```

（即在既有兩行之間插入那段 tailor 規則；其餘 _CONTRACT 內容不動。）

- [ ] **Step 6: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_apply.py tests/test_chat_tools.py -q`
Expected: PASS

- [ ] **Step 7: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠；既有合約/管道動作/prompt 測試不回歸）

- [ ] **Step 8: Commit**

```bash
git add sentinel/src/career_sentinel/chat.py sentinel/tests/test_chat_apply.py sentinel/tests/test_chat_tools.py
git commit -m "feat(sentinel): 聊天合約加 tailor 提議動作（客製化履歷/求職信）（#5）"
```

---

### Task 2: TailorCard ＋ 建議渲染分派（前端）

**Files:**
- Modify: `sentinel/web/frontend/src/ChatPage.tsx`

**Interfaces:**
- Consumes: 既有 `tailorApplication(job_url) -> Promise<Response>`、`openApplyPage(job_url) -> Promise<Response>`、`TailoredApplication` 型別（api.ts）；`field=="tailor"` 的 `SuggestedUpdate`（含 payload）。

- [ ] **Step 1: 補 import（`ChatPage.tsx`）**

`@mantine/core` import 加 `List`：

```tsx
import {
  ActionIcon, Alert, Badge, Button, Divider, Group, List, Loader, Paper, ScrollArea,
  Stack, Text, TextInput, TypographyStylesProvider,
} from "@mantine/core";
```

`@tabler/icons-react` import 加 `IconCheck, IconCopy, IconExternalLink`：

```tsx
import {
  IconBrain, IconCheck, IconCopy, IconDownload, IconEraser, IconExternalLink, IconSearch, IconTrash, IconX,
} from "@tabler/icons-react";
```

`./api` import 加 `openApplyPage, tailorApplication, type TailoredApplication`：

```tsx
import {
  applyUpdate, clearChat, deleteMemory, getChat, getResume, getSnapshot, openApplyPage, readSse,
  sendChat, SuggestedUpdate, tailorApplication, type RecommendedJob, type TailoredApplication,
} from "./api";
```

- [ ] **Step 2: 加 `TailorCard` 元件（`ChatPage.tsx`）**

在 `SuggestionCard` 元件之後加：

```tsx
function TailorCard({ payload }: { payload: { code: string; company?: string; title?: string } }) {
  const url = `https://www.104.com.tw/job/${payload.code}`;
  const [result, setResult] = useState<TailoredApplication | null>(null);
  const [busy, setBusy] = useState(false);
  const [applyBusy, setApplyBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [opened, setOpened] = useState(false);

  const runTailor = async () => {
    setErr(null); setBusy(true);
    try {
      const r = await tailorApplication(url);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "生成失敗"); return; }
      setResult(b as TailoredApplication);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  };

  const openApply = async () => {
    setErr(null); setApplyBusy(true); setOpened(false);
    try {
      const r = await openApplyPage(url);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "開啟失敗"); return; }
      setOpened(true);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setApplyBusy(false); }
  };

  const copyCover = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.cover_letter);
      setCopied(true); setTimeout(() => setCopied(false), 1500);
    } catch { setErr("複製失敗"); }
  };

  return (
    <Paper bg="dark.6" radius="md" px="md" py="sm" maw="92%">
      <Group justify="space-between" wrap="nowrap" mb={result ? "sm" : 0}>
        <Text size="sm"><b>客製化</b> {payload.company ?? ""}{payload.title ? ` · ${payload.title}` : ""}</Text>
        {!result && <Button size="compact-xs" loading={busy} onClick={runTailor}>客製化</Button>}
      </Group>
      {err && <Text size="xs" c="danger.6">{err}</Text>}
      {result && (
        <Stack gap="sm">
          {result.resume_tips.length > 0 && (
            <div>
              <Text fw={600} size="xs" mb={2}>要強調的重點</Text>
              <List size="xs" spacing={2}>{result.resume_tips.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
            </div>
          )}
          {result.resume_adjustments.length > 0 && (
            <div>
              <Text fw={600} size="xs" mb={2}>建議調整</Text>
              <List size="xs" spacing={2}>{result.resume_adjustments.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
            </div>
          )}
          {result.missing_keywords.length > 0 && (
            <div>
              <Text fw={600} size="xs" mb={2}>該補的關鍵字</Text>
              <Group gap={6}>{result.missing_keywords.map((k, i) => <Text key={i} size="xs" c="amber.5">{k}</Text>)}</Group>
            </div>
          )}
          <div>
            <Group justify="space-between" mb={2}>
              <Text fw={600} size="xs">求職信</Text>
              <ActionIcon variant="subtle" color="gray" size="sm" onClick={copyCover} title="複製求職信">
                {copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
              </ActionIcon>
            </Group>
            <Text size="xs" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{result.cover_letter}</Text>
          </div>
          <Group gap="sm">
            <Button size="compact-sm" leftSection={<IconExternalLink size={14} />} onClick={openApply} loading={applyBusy}>
              開 104 投遞頁
            </Button>
            {opened && <Text size="xs" c="teal.5">已在瀏覽器開啟投遞頁</Text>}
          </Group>
        </Stack>
      )}
    </Paper>
  );
}
```

- [ ] **Step 3: 建議渲染分派（`ChatPage.tsx`）**

把訊息渲染裡的：

```tsx
                {m.suggestions?.map((s, j) => <SuggestionCard key={j} s={s} />)}
```

改為：

```tsx
                {m.suggestions?.map((s, j) =>
                  s.field === "tailor"
                    ? <TailorCard key={j} payload={(s.payload ?? {}) as { code: string; company?: string; title?: string }} />
                    : <SuggestionCard key={j} s={s} />
                )}
```

- [ ] **Step 4: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 成功（`tsc -b && vite build` 無型別/未用 import 錯誤）

- [ ] **Step 5: Commit**

```bash
git add sentinel/web/frontend/src/ChatPage.tsx
git commit -m "feat(sentinel): 聊天 TailorCard——按鈕跑客製化+求職信+開104投遞頁（#5）"
```

---

## Self-Review

**Spec coverage：**
- 機制（tailor 提議走 <suggestions>、不走 apply_update）→ Task 1（合約）＋ Task 2（前端分派）✅
- 後端唯一改動（_CONTRACT 加 tailor 提議＋規則）→ Task 1 ✅
- TailorCard（按鈕跑 /api/tailor、渲染 tips/adjustments/missing/cover_letter 可複製、開 104 投遞頁）→ Task 2 ✅
- Global Constraints（成本按下才跑、不寫入 104、重用零新端點、不改 apply_update、需履歷錯誤顯示、相容）各 Task 遵守 ✅

**Placeholder scan：** 無 TBD/TODO；每步含完整程式碼與確切指令。

**Type consistency：** `tailor`/`run` 提議 field 於合約/測試/前端分派一致；payload `{code, company?, title?}` 於合約範例與 TailorCard props 一致；`tailorApplication`/`openApplyPage`/`TailoredApplication`（resume_tips/resume_adjustments/missing_keywords/cover_letter）與 api.ts 既有型別一致；url 由 code 組 `https://www.104.com.tw/job/${code}` 供 tailor 與 open 兩處共用。
