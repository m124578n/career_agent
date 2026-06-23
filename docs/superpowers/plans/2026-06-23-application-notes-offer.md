# 追蹤清單面試筆記 + Offer 記錄 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓使用者在追蹤清單針對每筆職缺記時間軸筆記與 offer 細節，並在多筆 offer 時並排比較。

**Architecture:** 後端沿用既有 `Application.events`（時間軸）並新增 `OfferInfo`/`Application.offer`，repository 加 `add_note`/`set_offer`，applications router 加 `POST /notes`、`PATCH /offer`。前端在看板卡片加 hint，點開右側 Drawer 顯示狀態/offer 表單/時間軸+加筆記；≥2 筆 offer 時 Offer 欄出現比較 Modal。

**Tech Stack:** 後端 FastAPI + Pydantic + Motor（測試用 pytest + mongomock_motor）；前端 React + Mantine + react-query + TypeScript。

## Global Constraints

- 後端測試框架：pytest，async 測試直接 `async def`，DB 用 `AsyncMongoMockClient()["test"]`
- 前端無單元測試框架；型別 gate 用 `frontend/node_modules/.bin/tsc.cmd --noEmit`（exit 0）
- 前端 types/index.ts 與後端 schema 為**手動同步**，欄位命名需一致（snake_case）
- 求職追蹤端點需登入、不耗 LLM 額度（沿用既有 router 風格）
- 新欄位一律 optional，沒填不顯示
- 薪資為自由文字字串；offer 表單只在 `status === "offer"` 顯示
- 後端工作目錄 `backend/`，測試指令 `uv run pytest`
- commit 不加 `--no-verify`

---

### Task 1: 後端 schema — OfferInfo 與 Application.offer

**Files:**
- Modify: `backend/src/job_tracker/schemas/__init__.py:96-115`
- Test: `backend/tests/test_schemas.py`

**Interfaces:**
- Produces:
  - `class OfferInfo(BaseModel)` 欄位皆 optional：`salary: str | None`、`level: str | None`、`start_date: str | None`、`accepted: bool | None`、`note: str | None`，預設都 `None`
  - `Application.offer: OfferInfo | None = None`

- [ ] **Step 1: 在 test_schemas.py 加失敗測試**

```python
def test_application_offer_defaults_none():
    from job_tracker.schemas import Application, Job
    job = Job(job_id="1", code="c1", title="工程師", company="某公司",
              url="https://www.104.com.tw/job/c1")
    app = Application(user="u1", job_id="1", job=job, source_search_id="s1")
    assert app.offer is None


def test_offer_info_all_optional():
    from job_tracker.schemas import OfferInfo
    o = OfferInfo()
    assert o.salary is None and o.accepted is None
    o2 = OfferInfo(salary="月 60k＋年終 2 個月", accepted=True)
    assert o2.salary == "月 60k＋年終 2 個月"
    assert o2.accepted is True
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_schemas.py::test_offer_info_all_optional -v`
Expected: FAIL — `ImportError: cannot import name 'OfferInfo'`

- [ ] **Step 3: 在 schemas/__init__.py 加 OfferInfo 並擴充 Application**

在 `class ApplicationEvent` 之後、`class Application` 之前插入：

```python
class OfferInfo(BaseModel):
    """offer 細節，全欄位 optional；薪資為自由文字。"""

    salary: str | None = None       # 自由文字，如「月 60k＋年終 2 個月」
    level: str | None = None        # 職等 / title
    start_date: str | None = None   # 到職日
    accepted: bool | None = None    # 是否接受
    note: str | None = None         # 補充
```

在 `class Application` 內，`events` 欄位後面加一行：

```python
    offer: OfferInfo | None = None
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_schemas.py -v`
Expected: PASS（含新增兩個測試）

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/schemas/__init__.py backend/tests/test_schemas.py
git commit -m "feat(schema): Application 加 OfferInfo 與 offer 欄位"
```

---

### Task 2: 後端 repository — add_note 與 set_offer

**Files:**
- Modify: `backend/src/job_tracker/db/repositories.py:234-251`（ApplicationRepository 內，`set_status` 之後）
- Test: `backend/tests/test_application_repository.py`

**Interfaces:**
- Consumes: Task 1 的 `OfferInfo`
- Produces（ApplicationRepository 方法）：
  - `async def add_note(self, user: str, job_id: str, note: str) -> Application | None` — push 一筆 `ApplicationEvent(type="note", note=note)`，更新 `updated_at`；找不到回 `None`
  - `async def set_offer(self, user: str, job_id: str, offer: OfferInfo) -> Application | None` — 整個覆蓋 `offer` 欄位，更新 `updated_at`；找不到回 `None`

- [ ] **Step 1: 加失敗測試**

在 `test_application_repository.py` 末尾加：

```python
async def test_add_note_appends_note_event(repo: ApplicationRepository):
    await repo.add(_app())
    updated = await repo.add_note("u1", "1", "一面聊得不錯")
    assert len(updated.events) == 1
    assert updated.events[0].type == "note"
    assert updated.events[0].note == "一面聊得不錯"


async def test_add_note_missing_returns_none(repo: ApplicationRepository):
    assert await repo.add_note("u1", "nope", "x") is None


async def test_set_offer_persists(repo: ApplicationRepository):
    from job_tracker.schemas import OfferInfo
    await repo.add(_app())
    updated = await repo.set_offer("u1", "1", OfferInfo(salary="月 60k", level="P5"))
    assert updated.offer.salary == "月 60k"
    assert updated.offer.level == "P5"


async def test_set_offer_missing_returns_none(repo: ApplicationRepository):
    from job_tracker.schemas import OfferInfo
    assert await repo.set_offer("u1", "nope", OfferInfo()) is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_application_repository.py::test_add_note_appends_note_event -v`
Expected: FAIL — `AttributeError: 'ApplicationRepository' object has no attribute 'add_note'`

- [ ] **Step 3: 實作兩個方法**

在 `repositories.py` 的 `ApplicationRepository.set_status` 方法之後、`remove` 之前插入（import 區已有 `ApplicationEvent`、`ApplicationStatus`；新增 import `OfferInfo`）：

先確認檔案頂部 `from job_tracker.schemas import (...)` 區塊加入 `OfferInfo`。

```python
    async def add_note(
        self, user: str, job_id: str, note: str
    ) -> Application | None:
        ev = ApplicationEvent(type="note", note=note)
        res = await self._col.update_one(
            {"_id": self._id(user, job_id)},
            {
                "$set": {"updated_at": ev.ts.isoformat()},
                "$push": {"events": ev.model_dump(mode="json")},
            },
        )
        if res.matched_count == 0:
            return None
        return await self.get(user, job_id)

    async def set_offer(
        self, user: str, job_id: str, offer: OfferInfo
    ) -> Application | None:
        from job_tracker.schemas import _utcnow

        res = await self._col.update_one(
            {"_id": self._id(user, job_id)},
            {"$set": {
                "offer": offer.model_dump(mode="json"),
                "updated_at": _utcnow().isoformat(),
            }},
        )
        if res.matched_count == 0:
            return None
        return await self.get(user, job_id)
```

注意：`_utcnow` 是 `schemas/__init__.py` 內既有的工具函式（`ApplicationEvent.ts` 用它當 default）。若它非以底線私有匯出，改用 `ApplicationEvent().ts` 取得當下時間亦可——確認後擇一，保持與 `set_status` 一致（`set_status` 用 `ev.ts`）。為與既有風格一致，改成：

```python
    async def set_offer(
        self, user: str, job_id: str, offer: OfferInfo
    ) -> Application | None:
        now = ApplicationEvent(type="offer").ts
        res = await self._col.update_one(
            {"_id": self._id(user, job_id)},
            {"$set": {
                "offer": offer.model_dump(mode="json"),
                "updated_at": now.isoformat(),
            }},
        )
        if res.matched_count == 0:
            return None
        return await self.get(user, job_id)
```

（採用後者，不需 import `_utcnow`。）

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_application_repository.py -v`
Expected: PASS（全部，含新增四個）

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/db/repositories.py backend/tests/test_application_repository.py
git commit -m "feat(repo): ApplicationRepository 加 add_note 與 set_offer"
```

---

### Task 3: 後端 API — POST /notes 與 PATCH /offer

**Files:**
- Modify: `backend/src/job_tracker/api/routers/applications.py`
- Test: `backend/tests/test_applications_api.py`

**Interfaces:**
- Consumes: Task 1 `OfferInfo`、Task 2 `add_note`/`set_offer`
- Produces（HTTP 端點，皆回傳 `Application`）：
  - `POST /applications/{job_id}/notes` body `{ "note": str }`
  - `PATCH /applications/{job_id}/offer` body 為 `OfferInfo`（部分欄位）

- [ ] **Step 1: 加失敗測試**

在 `test_applications_api.py` 末尾加：

```python
def test_add_note_and_set_offer_flow():
    db = AsyncMongoMockClient()["test"]
    sid = _seed(db)
    _wire(db)
    try:
        client = TestClient(app)
        client.post("/api/applications", json={"search_id": sid, "job_id": "1"})
        noted = client.post("/api/applications/1/notes", json={"note": "一面 ok"})
        offered = client.patch("/api/applications/1/offer",
                               json={"salary": "月 60k", "level": "P5"})
    finally:
        app.dependency_overrides.clear()

    assert noted.status_code == 200
    note_events = [e for e in noted.json()["events"] if e["type"] == "note"]
    assert note_events and note_events[0]["note"] == "一面 ok"
    assert offered.status_code == 200
    assert offered.json()["offer"]["salary"] == "月 60k"
    assert offered.json()["offer"]["level"] == "P5"


def test_note_on_missing_app_is_404():
    db = AsyncMongoMockClient()["test"]
    _seed(db)
    _wire(db)
    try:
        resp = TestClient(app).post("/api/applications/nope/notes",
                                    json={"note": "x"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 404
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_applications_api.py::test_add_note_and_set_offer_flow -v`
Expected: FAIL（404 或 405，因端點不存在）

- [ ] **Step 3: 實作端點**

在 `applications.py`：import 區的 `from job_tracker.schemas import ...` 加入 `OfferInfo`。在 `UpdateStatusRequest` 後加 request model：

```python
class AddNoteRequest(BaseModel):
    note: str
```

在 `update_status` 與 `remove_application` 之間加兩個端點：

```python
@router.post("/{job_id}/notes")
async def add_note(
    job_id: str,
    req: AddNoteRequest,
    user: str = Depends(current_user),
    app_repo: ApplicationRepository = Depends(get_application_repo),
) -> Application:
    updated = await app_repo.add_note(user, job_id, req.note)
    if updated is None:
        raise HTTPException(status_code=404, detail="找不到該追蹤項目")
    return updated


@router.patch("/{job_id}/offer")
async def set_offer(
    job_id: str,
    offer: OfferInfo,
    user: str = Depends(current_user),
    app_repo: ApplicationRepository = Depends(get_application_repo),
) -> Application:
    updated = await app_repo.set_offer(user, job_id, offer)
    if updated is None:
        raise HTTPException(status_code=404, detail="找不到該追蹤項目")
    return updated
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_applications_api.py -v`
Expected: PASS（全部）

- [ ] **Step 5: 全後端測試 regression**

Run: `cd backend && uv run pytest -q`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/src/job_tracker/api/routers/applications.py backend/tests/test_applications_api.py
git commit -m "feat(api): applications 加 POST /notes 與 PATCH /offer"
```

---

### Task 4: 前端 types 與 api client

**Files:**
- Modify: `frontend/src/types/index.ts:69-85`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Produces（前端）：
  - `interface OfferInfo { salary?: string | null; level?: string | null; start_date?: string | null; accepted?: boolean | null; note?: string | null }`
  - `Application.offer?: OfferInfo | null`
  - `api.addApplicationNote(jobId: string, note: string): Promise<Application>`
  - `api.setApplicationOffer(jobId: string, offer: OfferInfo): Promise<Application>`

- [ ] **Step 1: types/index.ts 加 OfferInfo 並擴充 Application**

在 `ApplicationEvent` 之後、`Application` 之前加：

```typescript
export interface OfferInfo {
  salary?: string | null;
  level?: string | null;
  start_date?: string | null;
  accepted?: boolean | null;
  note?: string | null;
}
```

在 `interface Application` 內 `events: ApplicationEvent[];` 後加一行：

```typescript
  offer?: OfferInfo | null;
```

- [ ] **Step 2: client.ts import 加 OfferInfo**

把 `import type { ... }` 區塊加入 `OfferInfo`（依字母序放在 `JobMatch` 前）：

```typescript
import type {
  Application,
  ApplicationStatus,
  JobMatch,
  OfferInfo,
  QuotaInfo,
  ResumeDiagnosis,
  ResumeTarget,
  SearchRun,
  UsageSummary,
} from "../types";
```

- [ ] **Step 3: client.ts 加兩個方法**

在 `removeApplication` 之後加：

```typescript
  addApplicationNote: (jobId: string, note: string) =>
    request<Application>(`/applications/${jobId}/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    }),
  setApplicationOffer: (jobId: string, offer: OfferInfo) =>
    request<Application>(`/applications/${jobId}/offer`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(offer),
    }),
```

- [ ] **Step 4: 型別檢查**

Run: `cd frontend && ./node_modules/.bin/tsc.cmd --noEmit`
Expected: exit 0（OfferInfo 已被使用，無未使用 import 錯誤）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts
git commit -m "feat(fe): types/client 加 OfferInfo 與 note/offer API"
```

---

### Task 5: 前端 Drawer — 卡片 hint、時間軸、加筆記、offer 表單

**Files:**
- Modify: `frontend/src/pages/Applications.tsx`

**Interfaces:**
- Consumes: Task 4 的 `api.addApplicationNote`、`api.setApplicationOffer`、`OfferInfo` 型別
- Produces: `AppCard` 點擊開 Drawer；Drawer 內含狀態下拉、offer 表單（僅 offer 狀態）、時間軸 + 加筆記輸入

- [ ] **Step 1: 改 AppCard — 加 hint 與點擊開 Drawer**

`Applications.tsx` 頂部 import 補上 Mantine 元件與 hooks 與型別：

```typescript
import {
  Box, Button, Drawer, Group, Select, Stack, Switch, Text, Textarea,
  TextInput, Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import type { Application, ApplicationStatus, OfferInfo } from "../types";
```

把 `AppCard` 整個替換為（卡片加 `💬n`/`💰` hint、整卡可點開 Drawer；狀態 Select 與 ✕ 用 `stopPropagation` 避免觸發 Drawer）：

```typescript
function AppCard({ app }: { app: Application }) {
  const qc = useQueryClient();
  const [opened, { open, close }] = useDisclosure(false);
  const statusMut = useMutation({
    mutationFn: (status: ApplicationStatus) =>
      api.updateApplicationStatus(app.job_id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });
  const removeMut = useMutation({
    mutationFn: () => api.removeApplication(app.job_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });

  const noteCount = app.events.filter((e) => e.type === "note").length;
  const hasOffer = !!app.offer;

  return (
    <>
      <div className="jt-jobcard" style={{ cursor: "pointer" }} onClick={open}>
        <Group justify="space-between" wrap="nowrap" mb={6}>
          <span className="jt-job-title">{app.job.title}</span>
          <Text fz="xs" c="dimmed" style={{ cursor: "pointer" }}
                onClick={(e) => { e.stopPropagation(); removeMut.mutate(); }}>
            ✕
          </Text>
        </Group>
        <div className="jt-job-meta">{app.job.company}</div>
        <Group gap={8} mt={6}>
          {noteCount > 0 && <Text fz="xs" c="dimmed">💬 {noteCount}</Text>}
          {hasOffer && <Text fz="xs" c="dimmed">💰</Text>}
        </Group>
        <div onClick={(e) => e.stopPropagation()}>
          <Select
            mt={8}
            size="xs"
            value={app.status}
            data={COLUMNS.map((c) => ({ value: c.status, label: c.label }))}
            onChange={(v) => v && statusMut.mutate(v as ApplicationStatus)}
            allowDeselect={false}
          />
        </div>
      </div>
      <AppDrawer app={app} opened={opened} onClose={close} />
    </>
  );
}
```

- [ ] **Step 2: 新增 AppDrawer 元件**

在 `AppCard` 之後加（時間軸倒序、status/note 不同樣式；底部加筆記；offer 表單僅 `status === "offer"`）：

```typescript
function AppDrawer({
  app, opened, onClose,
}: { app: Application; opened: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const [offer, setOffer] = useState<OfferInfo>(app.offer ?? {});

  const noteMut = useMutation({
    mutationFn: (note: string) => api.addApplicationNote(app.job_id, note),
    onSuccess: () => {
      setDraft("");
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
  });
  const offerMut = useMutation({
    mutationFn: (o: OfferInfo) => api.setApplicationOffer(app.job_id, o),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });

  const events = [...app.events].reverse();
  const set = (k: keyof OfferInfo, v: string) =>
    setOffer((o) => ({ ...o, [k]: v }));
  const setAccepted = (v: boolean) => setOffer((o) => ({ ...o, accepted: v }));

  return (
    <Drawer opened={opened} onClose={onClose} position="right" size="md"
            title={<span className="jt-eyebrow">{app.job.company} · {app.job.title}</span>}>
      <Stack gap={16}>
        {app.status === "offer" && (
          <div>
            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>OFFER</div>
            <Stack gap={8}>
              <TextInput size="xs" label="薪資" placeholder="月 60k＋年終 2 個月"
                         value={offer.salary ?? ""} onChange={(e) => set("salary", e.currentTarget.value)} />
              <TextInput size="xs" label="職等 / Title" value={offer.level ?? ""}
                         onChange={(e) => set("level", e.currentTarget.value)} />
              <TextInput size="xs" label="到職日" placeholder="2026-08-01"
                         value={offer.start_date ?? ""} onChange={(e) => set("start_date", e.currentTarget.value)} />
              <TextInput size="xs" label="備註" value={offer.note ?? ""}
                         onChange={(e) => set("note", e.currentTarget.value)} />
              <Switch size="sm" label="已接受這個 offer"
                      checked={offer.accepted ?? false}
                      onChange={(e) => setAccepted(e.currentTarget.checked)} />
              <Button size="xs" variant="default" loading={offerMut.isPending}
                      onClick={() => offerMut.mutate(offer)}>儲存 Offer</Button>
            </Stack>
          </div>
        )}

        <div>
          <div className="jt-eyebrow" style={{ marginBottom: 8 }}>時間軸</div>
          <Stack gap={6}>
            {events.length === 0 ? (
              <Text fz="xs" c="dimmed">—</Text>
            ) : (
              events.map((e, i) => (
                <Group key={i} gap={8} wrap="nowrap" align="flex-start">
                  <Text fz="xs" c="dimmed" style={{ minWidth: 92 }}>
                    {new Date(e.ts).toLocaleString("zh-TW",
                      { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                  </Text>
                  <Text fz="xs" c={e.type === "note" ? undefined : "teal"}>
                    {e.type === "note" ? e.note : `狀態 ${e.note}`}
                  </Text>
                </Group>
              ))
            )}
          </Stack>
          <Group gap={8} mt={10} align="flex-end">
            <Textarea size="xs" style={{ flex: 1 }} autosize minRows={1} maxRows={4}
                      placeholder="加一條筆記…" value={draft}
                      onChange={(e) => setDraft(e.currentTarget.value)} />
            <Button size="xs" color="tangerine" loading={noteMut.isPending}
                    disabled={!draft.trim()}
                    onClick={() => noteMut.mutate(draft.trim())}>加入</Button>
          </Group>
        </div>
      </Stack>
    </Drawer>
  );
}
```

- [ ] **Step 3: 型別檢查**

Run: `cd frontend && ./node_modules/.bin/tsc.cmd --noEmit`
Expected: exit 0

- [ ] **Step 4: 手動驗證（後端與前端 dev server 已在跑）**

- 開啟追蹤清單頁，把一筆切到「面試中」→ 點卡片，Drawer 從右滑出
- 在時間軸底部加一條筆記 → 送出後時間軸出現該筆記、卡片顯示 `💬 1`
- 把該筆切到「Offer」→ 重新點開 Drawer，出現 Offer 表單；填薪資後「儲存 Offer」→ 卡片出現 `💰`
- 確認狀態下拉與 ✕ 點擊不會誤觸開 Drawer

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Applications.tsx
git commit -m "feat(fe): 追蹤卡片開 Drawer，時間軸筆記與 offer 表單"
```

---

### Task 6: 前端 Offer 比較 Modal

**Files:**
- Modify: `frontend/src/pages/Applications.tsx`

**Interfaces:**
- Consumes: `apps`（已在 `Applications` 元件）、`OfferInfo`
- Produces: 當 ≥2 筆 `status === "offer"`，Offer 欄頂端「比較」按鈕 → 開並排表格 Modal

- [ ] **Step 1: import 補 Modal、Table**

把 Task 5 的 import 行擴充加入 `Modal, Table`：

```typescript
import {
  Box, Button, Drawer, Group, Modal, Select, Stack, Table, Text, Textarea,
  TextInput, Title,
} from "@mantine/core";
```

- [ ] **Step 2: 在欄位 head 加比較按鈕（僅 Offer 欄、≥2 筆）**

把 `Applications` 元件裡欄位的 `jt-panel-head` 區塊替換為條件式渲染比較按鈕：

```typescript
              <div className="jt-panel-head">
                <span className="jt-eyebrow">{col.label} · {items.length}</span>
                {col.status === "offer" && items.length >= 2 && (
                  <CompareButton offers={items} />
                )}
              </div>
```

- [ ] **Step 3: 新增 CompareButton 元件**

在檔案末尾加（並排表格：公司 / 薪資 / 職等 / 到職日 / 備註）：

```typescript
function CompareButton({ offers }: { offers: Application[] }) {
  const [opened, { open, close }] = useDisclosure(false);
  return (
    <>
      <Button size="xs" variant="default" onClick={open}>比較</Button>
      <Modal opened={opened} onClose={close} size="lg"
             title={<span className="jt-eyebrow">OFFER 比較</span>}>
        <Table withTableBorder withColumnBorders fz="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>公司</Table.Th>
              <Table.Th>薪資</Table.Th>
              <Table.Th>職等</Table.Th>
              <Table.Th>到職日</Table.Th>
              <Table.Th>備註</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {offers.map((a) => (
              <Table.Tr key={a.job_id}>
                <Table.Td>{a.job.company}</Table.Td>
                <Table.Td>{a.offer?.salary ?? "—"}</Table.Td>
                <Table.Td>{a.offer?.level ?? "—"}</Table.Td>
                <Table.Td>{a.offer?.start_date ?? "—"}</Table.Td>
                <Table.Td>{a.offer?.note ?? "—"}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Modal>
    </>
  );
}
```

- [ ] **Step 4: 型別檢查**

Run: `cd frontend && ./node_modules/.bin/tsc.cmd --noEmit`
Expected: exit 0

- [ ] **Step 5: 手動驗證**

- 讓 ≥2 筆處於「Offer」狀態並各填一些 offer 欄位
- Offer 欄頂端出現「比較」→ 點開 Modal，表格並排顯示各 offer
- 只剩 1 筆 offer 時「比較」按鈕消失

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Applications.tsx
git commit -m "feat(fe): 多筆 offer 並排比較 Modal"
```

---

## Self-Review 註記

- **Spec coverage**：schema(T1)、API(T3)、repo(T2)、卡片 hint+Drawer+時間軸+加筆記+offer 表單(T5)、compare(T6)、types/client(T4) 皆有對應任務。
- **薪資自由文字**：T1 `salary: str | None`、T5 TextInput；無排序邏輯，符合 spec。
- **offer 表單只在 offer 狀態**：T5 `app.status === "offer"` 條件渲染。
- **型別一致**：`OfferInfo` 欄位（salary/level/start_date/accepted/note）前後端命名一致；`add_note`/`set_offer`/`addApplicationNote`/`setApplicationOffer` 簽名跨任務一致。
- **accepted**：後端 schema(T1) 含、offer 表單(T5)以 Switch 提供；compare 表格(T6)不顯示 accepted（spec 比較欄位為薪資/職等/到職日/備註，符合）。
