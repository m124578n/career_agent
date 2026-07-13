# 線上版意見回饋（私密收件匣）實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為線上版加意見回饋：登入者送出、admin 私密收件匣（列表/已讀/刪除）。

**Architecture:** 後端 `feedback` collection + `FeedbackRepository` + `Feedback` schema + `/feedback` router（POST 任何登入者、GET/read/DELETE admin-gated）；前端側欄「意見回饋」送出 Modal（所有登入者）+ `/admin` 頁下方 admin 收件匣區塊。

**Tech Stack:** FastAPI + Motor(MongoDB) + Pydantic；React + Vite + TS + Mantine + TanStack Query。

## Global Constraints

- 私密：`POST /feedback` 任何登入者可送；`GET/POST(read)/DELETE` 僅 admin（`auth.is_admin`，非 admin → 403）。
- `message` strip 後空 → 400；> 2000 字 → 400；`category` ∈ {建議, 問題回報, 其他}，否則用「其他」。
- 沿用既有 repo 模式（`db/repositories.py` + `deps.get_X_repo`）、schemas 集中於 `schemas/__init__.py`、router 註冊於 `api/routers/__init__.py`、`/api` 前綴、mongomock 測試 + `dependency_overrides` + monkeypatch `is_admin`。
- 後端測試：`cd backend && uv run pytest -q`；前端：`cd frontend && npm run build`。
- **不 merge 到 main**（使用者自行 review／決定部署）。

---

## 檔案結構

```
backend/src/job_tracker/
├─ schemas/__init__.py          # + class Feedback
├─ db/repositories.py           # + class FeedbackRepository
├─ api/deps.py                  # + get_feedback_repo
├─ api/routers/feedback.py      # 新：/feedback 端點
└─ api/routers/__init__.py      # 註冊 feedback router
frontend/src/
├─ api/client.ts                # + Feedback 型別 + 4 個方法
├─ components/FeedbackButton.tsx # 新：送出 Modal（側欄）
├─ components/FeedbackInbox.tsx  # 新：admin 收件匣
├─ App.tsx                      # 側欄放 FeedbackButton
└─ pages/AdminStats.tsx         # 底部放 FeedbackInbox
backend/tests/
├─ test_feedback_repository.py
└─ test_feedback_api.py
```

---

### Task 1: 後端 `Feedback` schema + `FeedbackRepository` + dep

**Files:**
- Modify: `backend/src/job_tracker/schemas/__init__.py`
- Modify: `backend/src/job_tracker/db/repositories.py`
- Modify: `backend/src/job_tracker/api/deps.py`
- Test: `backend/tests/test_feedback_repository.py`

**Interfaces:**
- Produces: `schemas.Feedback(id,user,message,category,created_at,read)`；`FeedbackRepository.create(user,message,category)->Feedback` / `.list()->list[Feedback]`（新→舊）/ `.mark_read(fid,read)` / `.delete(fid)`；`deps.get_feedback_repo()->FeedbackRepository`。

- [ ] **Step 1: 加 `Feedback` schema**

在 `backend/src/job_tracker/schemas/__init__.py` 末尾加（沿用檔內既有 `BaseModel` import）：

```python
class Feedback(BaseModel):
    id: str = ""
    user: str = ""
    message: str = ""
    category: str = "其他"
    created_at: str = ""
    read: bool = False
```

- [ ] **Step 2: 寫失敗測試**

建立 `backend/tests/test_feedback_repository.py`：

```python
import asyncio

from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import FeedbackRepository


def _repo():
    return FeedbackRepository(AsyncMongoMockClient()["test"])


def test_create_sets_fields():
    repo = _repo()
    fb = asyncio.run(repo.create("a@x.com", " 很好用 ", "建議"))
    assert fb.user == "a@x.com" and fb.message == " 很好用 " and fb.category == "建議"
    assert fb.read is False and fb.id and fb.created_at


def test_list_newest_first():
    repo = _repo()
    a = asyncio.run(repo.create("a@x.com", "first", "其他"))
    b = asyncio.run(repo.create("b@x.com", "second", "其他"))
    items = asyncio.run(repo.list())
    assert [i.id for i in items] == [b.id, a.id]  # 新→舊
    assert all(i.id for i in items)  # id 有從 _id 帶回


def test_mark_read_and_delete():
    repo = _repo()
    fb = asyncio.run(repo.create("a@x.com", "x", "其他"))
    asyncio.run(repo.mark_read(fb.id, True))
    assert asyncio.run(repo.list())[0].read is True
    asyncio.run(repo.delete(fb.id))
    assert asyncio.run(repo.list()) == []
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_feedback_repository.py -q`
Expected: FAIL（`FeedbackRepository` 不存在）

- [ ] **Step 4: 實作 `FeedbackRepository`**

在 `backend/src/job_tracker/db/repositories.py`：檔頭 import 區加 `import uuid`、`from datetime import UTC, datetime`（若尚未 import；`datetime`/`UTC` 檔內已用）、`Feedback`（加進既有 `from job_tracker.schemas import (...)`）。在檔案末尾加：

```python
class FeedbackRepository:
    """意見回饋（私密；admin 收件匣）。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["feedback"]

    async def create(self, user: str, message: str, category: str) -> Feedback:
        fb = Feedback(
            id=str(uuid.uuid4()), user=user, message=message, category=category,
            created_at=datetime.now(UTC).isoformat(), read=False,
        )
        doc = fb.model_dump()
        doc["_id"] = doc.pop("id")
        await self._col.insert_one(doc)
        return fb

    async def list(self) -> list[Feedback]:
        cur = self._col.find({}).sort("created_at", -1)
        return [Feedback(**{**doc, "id": doc["_id"]}) async for doc in cur]

    async def mark_read(self, fid: str, read: bool) -> None:
        await self._col.update_one({"_id": fid}, {"$set": {"read": read}})

    async def delete(self, fid: str) -> None:
        await self._col.delete_one({"_id": fid})
```

- [ ] **Step 5: 加 `get_feedback_repo` 依賴**

在 `backend/src/job_tracker/api/deps.py`：把 `FeedbackRepository` 加進 `from job_tracker.db.repositories import (...)`；`__all__` 加 `"get_feedback_repo"`；加函式（與其他 `get_*_repo` 並列）：

```python
def get_feedback_repo() -> FeedbackRepository:
    return FeedbackRepository(get_db())
```

- [ ] **Step 6: 跑測試確認通過（含後端全套）**

Run: `cd backend && uv run pytest -q`
Expected: 既有全綠 + 3 新測試通過。

- [ ] **Step 7: Commit**

```bash
git add backend/src/job_tracker/schemas/__init__.py backend/src/job_tracker/db/repositories.py backend/src/job_tracker/api/deps.py backend/tests/test_feedback_repository.py
git commit -m "feat(online): Feedback schema + FeedbackRepository + dep"
```

---

### Task 2: 後端 `/feedback` router

**Files:**
- Create: `backend/src/job_tracker/api/routers/feedback.py`
- Modify: `backend/src/job_tracker/api/routers/__init__.py`
- Test: `backend/tests/test_feedback_api.py`

**Interfaces:**
- Consumes: `FeedbackRepository`、`deps.get_feedback_repo`、`deps.current_user`、`auth.is_admin`、`schemas.Feedback`。
- Produces: `POST /api/feedback`、`GET /api/feedback`、`POST /api/feedback/{fid}/read`、`DELETE /api/feedback/{fid}`。

- [ ] **Step 1: 寫失敗測試**

建立 `backend/tests/test_feedback_api.py`：

```python
import asyncio

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.api.routers import feedback as feedback_router
from job_tracker.db.repositories import FeedbackRepository
from job_tracker.main import app


def _client_with(repo):
    app.dependency_overrides[deps.get_feedback_repo] = lambda: repo
    return TestClient(app)


def test_submit_ok_for_any_user():
    repo = FeedbackRepository(AsyncMongoMockClient()["test"])
    try:
        r = _client_with(repo).post("/api/feedback", json={"message": "很好用", "category": "建議"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200 and r.json()["ok"] is True
    assert asyncio.run(repo.list())[0].message == "很好用"


def test_submit_empty_400():
    repo = FeedbackRepository(AsyncMongoMockClient()["test"])
    try:
        r = _client_with(repo).post("/api/feedback", json={"message": "   "})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 400


def test_submit_too_long_400():
    repo = FeedbackRepository(AsyncMongoMockClient()["test"])
    try:
        r = _client_with(repo).post("/api/feedback", json={"message": "x" * 2001})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 400


def test_list_admin_ok_nonadmin_403():
    repo = FeedbackRepository(AsyncMongoMockClient()["test"])
    asyncio.run(repo.create("u@x.com", "hi", "其他"))
    # admin（dev 模式）
    try:
        r = _client_with(repo).get("/api/feedback")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200 and len(r.json()) == 1


def test_list_forbidden_for_nonadmin(monkeypatch):
    repo = FeedbackRepository(AsyncMongoMockClient()["test"])
    monkeypatch.setattr(feedback_router, "is_admin", lambda user: False)
    try:
        r = _client_with(repo).get("/api/feedback")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 403


def test_read_and_delete_admin(monkeypatch):
    repo = FeedbackRepository(AsyncMongoMockClient()["test"])
    fb = asyncio.run(repo.create("u@x.com", "hi", "其他"))
    c = _client_with(repo)
    try:
        assert c.post(f"/api/feedback/{fb.id}/read", json={"read": True}).status_code == 200
        assert asyncio.run(repo.list())[0].read is True
        assert c.delete(f"/api/feedback/{fb.id}").status_code == 200
        assert asyncio.run(repo.list()) == []
        # 非 admin 被擋
        monkeypatch.setattr(feedback_router, "is_admin", lambda user: False)
        assert c.delete("/api/feedback/whatever").status_code == 403
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_feedback_api.py -q`
Expected: FAIL（404）

- [ ] **Step 3: 建立 router**

建立 `backend/src/job_tracker/api/routers/feedback.py`：

```python
"""意見回饋端點：登入者送出；admin 私密收件匣（列表/已讀/刪除）。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from job_tracker.api.deps import current_user, get_feedback_repo
from job_tracker.auth import is_admin
from job_tracker.db.repositories import FeedbackRepository
from job_tracker.schemas import Feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])

_CATEGORIES = {"建議", "問題回報", "其他"}
_MAX_LEN = 2000


class SubmitFeedbackRequest(BaseModel):
    message: str
    category: str = "其他"


class ReadRequest(BaseModel):
    read: bool


@router.post("")
async def submit_feedback(
    req: SubmitFeedbackRequest,
    user: str = Depends(current_user),
    repo: FeedbackRepository = Depends(get_feedback_repo),
) -> dict:
    msg = req.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="請輸入內容")
    if len(msg) > _MAX_LEN:
        raise HTTPException(status_code=400, detail="內容過長（上限 2000 字）")
    category = req.category if req.category in _CATEGORIES else "其他"
    await repo.create(user, msg, category)
    return {"ok": True}


@router.get("")
async def list_feedback(
    user: str = Depends(current_user),
    repo: FeedbackRepository = Depends(get_feedback_repo),
) -> list[Feedback]:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="僅管理者可檢視")
    return await repo.list()


@router.post("/{fid}/read")
async def set_feedback_read(
    fid: str,
    req: ReadRequest,
    user: str = Depends(current_user),
    repo: FeedbackRepository = Depends(get_feedback_repo),
) -> dict:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="僅管理者可操作")
    await repo.mark_read(fid, req.read)
    return {"ok": True}


@router.delete("/{fid}")
async def delete_feedback(
    fid: str,
    user: str = Depends(current_user),
    repo: FeedbackRepository = Depends(get_feedback_repo),
) -> dict:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="僅管理者可操作")
    await repo.delete(fid)
    return {"ok": True}
```

- [ ] **Step 4: 註冊 router**

在 `backend/src/job_tracker/api/routers/__init__.py`：`from job_tracker.api.routers import ...` 加入 `feedback`；並在 include 區加 `api_router.include_router(feedback.router)`。

- [ ] **Step 5: 跑測試確認通過（含後端全套）**

Run: `cd backend && uv run pytest -q`
Expected: 全綠 + 6 新測試通過。

- [ ] **Step 6: Commit**

```bash
git add backend/src/job_tracker/api/routers/feedback.py backend/src/job_tracker/api/routers/__init__.py backend/tests/test_feedback_api.py
git commit -m "feat(online): /feedback 端點（送出開放、讀取/刪除 admin-gated）"
```

---

### Task 3: 前端 api client + 送出 Modal（側欄）

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/components/FeedbackButton.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: 既有 `request<T>` helper、`notifications`。
- Produces: `api.submitFeedback/listFeedback/markFeedbackRead/deleteFeedback`；`Feedback` 型別；`<FeedbackButton />`（側欄）。

- [ ] **Step 1: api client 型別與方法**

在 `frontend/src/api/client.ts` 適當處加型別，並在 `export const api = {` 物件內加 4 個方法（與 `adminStats` 等同風格）：

```typescript
export interface Feedback {
  id: string;
  user: string;
  message: string;
  category: string;
  created_at: string;
  read: boolean;
}
```

```typescript
  submitFeedback: (message: string, category: string) =>
    request<{ ok: boolean }>("/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, category }),
    }),
  listFeedback: () => request<Feedback[]>("/feedback"),
  markFeedbackRead: (id: string, read: boolean) =>
    request<{ ok: boolean }>(`/feedback/${encodeURIComponent(id)}/read`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ read }),
    }),
  deleteFeedback: (id: string) =>
    request<{ ok: boolean }>(`/feedback/${encodeURIComponent(id)}`, { method: "DELETE" }),
```

- [ ] **Step 2: 建立 `FeedbackButton.tsx`**

建立 `frontend/src/components/FeedbackButton.tsx`：

```tsx
import { Button, Group, Modal, Select, Stack, Text, Textarea, UnstyledButton } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { api } from "../api/client";

const CATEGORIES = ["建議", "問題回報", "其他"];

export function FeedbackButton() {
  const [opened, { open, close }] = useDisclosure(false);
  const [message, setMessage] = useState("");
  const [category, setCategory] = useState<string>("建議");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!message.trim()) return;
    setErr(null); setBusy(true);
    try {
      await api.submitFeedback(message.trim(), category);
      setMessage("");
      close();
      notifications.show({ color: "teal", title: "已送出", message: "感謝你的回饋！" });
    } catch {
      setErr("送出失敗，請稍後再試。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <UnstyledButton onClick={open} style={{ padding: "6px 8px", borderRadius: 8 }}>
        <Text fz={12} c="dimmed">💬 意見回饋</Text>
      </UnstyledButton>
      <Modal opened={opened} onClose={close} title="意見回饋" centered>
        <Stack gap="sm">
          <Select label="類別" data={CATEGORIES} value={category}
            onChange={(v) => setCategory(v ?? "其他")} allowDeselect={false} />
          <Textarea label="內容" placeholder="想給我們的建議、遇到的問題…" minRows={4} autosize
            maxLength={2000} value={message} onChange={(e) => setMessage(e.currentTarget.value)} />
          {err && <Text c="danger.5" fz="sm">{err}</Text>}
          <Group justify="flex-end">
            <Button variant="subtle" color="gray" onClick={close}>取消</Button>
            <Button color="tangerine" loading={busy} disabled={!message.trim()} onClick={submit}>送出</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
```

- [ ] **Step 3: App.tsx 側欄放按鈕**

在 `frontend/src/App.tsx`：import 加 `import { FeedbackButton } from "./components/FeedbackButton";`。在 navbar 底部 `<div style={{ marginTop: "auto" }}>` 內、`<AccountFooter />` 之前加一行：

```tsx
          <FeedbackButton />
```

- [ ] **Step 4: 前端建置**

Run: `cd frontend && npm run build`
Expected: build 成功、無型別錯誤。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/components/FeedbackButton.tsx frontend/src/App.tsx
git commit -m "feat(online): 側欄意見回饋送出 Modal + api client"
```

---

### Task 4: 前端 admin 收件匣（AdminStats 頁）

**Files:**
- Create: `frontend/src/components/FeedbackInbox.tsx`
- Modify: `frontend/src/pages/AdminStats.tsx`

**Interfaces:**
- Consumes: `api.listFeedback/markFeedbackRead/deleteFeedback`、`Feedback` 型別（Task 3）。

- [ ] **Step 1: 建立 `FeedbackInbox.tsx`**

建立 `frontend/src/components/FeedbackInbox.tsx`：

```tsx
import { ActionIcon, Badge, Group, Loader, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Feedback } from "../api/client";

export function FeedbackInbox() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["feedback"], queryFn: api.listFeedback });
  const readMut = useMutation({
    mutationFn: ({ id, read }: { id: string; read: boolean }) => api.markFeedbackRead(id, read),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feedback"] }),
  });
  const delMut = useMutation({
    mutationFn: (id: string) => api.deleteFeedback(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feedback"] }),
  });

  const items = data ?? [];
  const unread = items.filter((f) => !f.read).length;

  return (
    <div className="jt-panel" style={{ marginTop: 28 }}>
      <div className="jt-panel-body">
        <Group justify="space-between" mb="md">
          <Text fw={600} fz="sm">意見回饋收件匣</Text>
          {unread > 0 && <Badge color="tangerine">{unread} 未讀</Badge>}
        </Group>
        {isLoading ? (
          <Loader size="sm" />
        ) : items.length === 0 ? (
          <Text fz="sm" c="dimmed">目前沒有回饋。</Text>
        ) : (
          <Stack gap={10}>
            {items.map((f: Feedback) => (
              <div key={f.id} style={{
                borderLeft: `3px solid ${f.read ? "var(--jt-border)" : "var(--jt-tangerine, #e8a05a)"}`,
                paddingLeft: 12,
              }}>
                <Group justify="space-between" wrap="nowrap" gap={8}>
                  <Group gap={8} wrap="nowrap">
                    <Badge size="xs" variant="light">{f.category}</Badge>
                    <Text fz={11} c="dimmed">{f.user}</Text>
                    <Text fz={11} c="dimmed">{new Date(f.created_at).toLocaleString("zh-TW")}</Text>
                  </Group>
                  <Group gap={4} wrap="nowrap" style={{ flexShrink: 0 }}>
                    <ActionIcon size="sm" variant="subtle" color="gray" title={f.read ? "標為未讀" : "標為已讀"}
                      onClick={() => readMut.mutate({ id: f.id, read: !f.read })}>
                      {f.read ? "↺" : "✓"}
                    </ActionIcon>
                    <ActionIcon size="sm" variant="subtle" color="red" title="刪除"
                      onClick={() => delMut.mutate(f.id)}>✕</ActionIcon>
                  </Group>
                </Group>
                <Text fz="sm" mt={4} style={{ whiteSpace: "pre-wrap" }}>{f.message}</Text>
              </div>
            ))}
          </Stack>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: AdminStats 頁掛載**

在 `frontend/src/pages/AdminStats.tsx`：import 加 `import { FeedbackInbox } from "../components/FeedbackInbox";`。在頁面主要內容的最外層 `<Box ...>` 內、每日活躍趨勢 `<div className="jt-panel">...</div>` 之後（`</Box>` 之前）加一行：

```tsx
      <FeedbackInbox />
```

（`FeedbackInbox` 自帶 `["feedback"]` query；因整頁已 admin-gated，非 admin 不會到這裡。）

- [ ] **Step 3: 前端建置**

Run: `cd frontend && npm run build`
Expected: build 成功、無型別錯誤。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/FeedbackInbox.tsx frontend/src/pages/AdminStats.tsx
git commit -m "feat(online): admin 意見回饋收件匣（AdminStats 頁）"
```

---

## Self-Review

**1. Spec coverage：** schema+repo+dep（Task 1）、`/feedback` 端點（Task 2，POST 開放、GET/read/DELETE admin 403、空/過長 400、category 白名單）、送出 Modal（Task 3）、admin 收件匣（Task 4）全覆蓋。私密（只 admin 讀）、登入才送、2000 上限、放 /admin 頁下方——皆遵守。非目標（不公開/不回覆串/不通知/不匿名）遵守。

**2. Placeholder scan：** 無 TBD/TODO；每步含完整程式碼；測試含實際斷言與預期。

**3. Type/名稱一致性：** `Feedback`（id/user/message/category/created_at/read）在 schema、repo、端點回傳、前端型別、兩個元件間一致；`FeedbackRepository.create/list/mark_read/delete`、`get_feedback_repo`、`submitFeedback/listFeedback/markFeedbackRead/deleteFeedback`、query key `["feedback"]`、router 路徑 `/api/feedback` 與 `{fid}/read`、`_CATEGORIES` 與前端 `CATEGORIES` 一致；`is_admin` monkeypatch 目標為 `feedback_router.is_admin`（端點 import 到自身命名空間）。
