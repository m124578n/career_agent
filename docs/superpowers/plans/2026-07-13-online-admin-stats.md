# 線上版 admin 營運數據 dashboard 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為線上版加一頁只有 admin 看得到的營運數據（使用人數/活躍/用量 + 近 30 天活躍趨勢），從既有 MongoDB collection 聚合。

**Architecture:** 後端 `services/admin_stats.py` 純聚合（Python 端統計、可用 mongomock 測）+ `GET /usage/admin-stats`（admin-gated）；前端 `AdminStats.tsx` 頁 + `/admin` 路由 + 依 `quota.is_admin` 條件顯示的 nav。

**Tech Stack:** FastAPI + Motor(MongoDB) + Pydantic；React + Vite + TS + Mantine + react-router + TanStack Query。

## Global Constraints

- 從既有 collection 聚合（`daily_usage`/`searches`/`matches`/`applications`/`token_usage`），不新增事件追蹤。
- `total_users`=`daily_usage` distinct user；`active_7d`/`active_30d`=近 7/30 天窗（含今天，UTC，`day` 為 `YYYY-MM-DD` 字串字典序比較）distinct user；`total_analyzed`=`matches` status==done；`tokens`/`llm_calls` 來自 `TokenUsageRepository.summary()`（total_tokens/calls；無成本）。`daily_active`=連續 30 天、缺日補 0。
- admin-gated：`GET /usage/admin-stats` 非 admin → 403（沿用 `auth.is_admin`）；前端 `/admin` 與 nav 僅 `quota.is_admin` 顯示。
- 不加前端圖表套件（純 CSS 長條）。
- 後端測試：`cd backend && uv run pytest -q`；前端：`cd frontend && npm run build`。
- **不 merge 到 main**（使用者會自行 review／決定部署；merge main 會自動部署）。

---

## 檔案結構

```
backend/src/job_tracker/
├─ services/admin_stats.py     # 新：DailyActive/AdminStats + compute_admin_stats
├─ api/deps.py                 # + get_database 依賴
└─ api/routers/usage.py        # + GET /usage/admin-stats
frontend/src/
├─ api/client.ts               # + AdminStats 型別 + adminStats()
├─ pages/AdminStats.tsx        # 新：營運數據頁
├─ main.tsx                    # + /admin 路由（GatedShell 下）
└─ App.tsx                     # nav 依 quota.is_admin 加「營運數據」
backend/tests/
├─ test_admin_stats.py         # 新：compute_admin_stats 聚合
└─ test_admin_stats_api.py     # 新：端點 admin/非 admin
```

---

### Task 1: 後端聚合服務 `admin_stats.py`

**Files:**
- Create: `backend/src/job_tracker/services/admin_stats.py`
- Test: `backend/tests/test_admin_stats.py`

**Interfaces:**
- Consumes: Motor db handle（有 `daily_usage`/`searches`/`matches`/`applications`/`token_usage` collection）；`TokenUsageRepository`。
- Produces: `admin_stats.DailyActive(day: str, users: int)`；`admin_stats.AdminStats`（欄位見下）；`async def compute_admin_stats(db) -> AdminStats`。

- [ ] **Step 1: 寫失敗測試**

建立 `backend/tests/test_admin_stats.py`：

```python
import asyncio
from datetime import UTC, datetime, timedelta

from mongomock_motor import AsyncMongoMockClient

from job_tracker.services.admin_stats import compute_admin_stats


def _day(offset: int) -> str:
    return (datetime.now(UTC).date() - timedelta(days=offset)).isoformat()


def _seed(db):
    du = db["daily_usage"]
    # 三個使用者：a 今天、b 5 天前、c 20 天前
    asyncio.run(du.insert_many([
        {"_id": f"a|{_day(0)}", "user": "a", "day": _day(0), "count": 3},
        {"_id": f"b|{_day(5)}", "user": "b", "day": _day(5), "count": 1},
        {"_id": f"c|{_day(20)}", "user": "c", "day": _day(20), "count": 2},
    ]))
    asyncio.run(db["searches"].insert_many([{"_id": "s1"}, {"_id": "s2"}]))
    asyncio.run(db["matches"].insert_many([
        {"_id": "m1", "status": "done"}, {"_id": "m2", "status": "done"},
        {"_id": "m3", "status": "candidate"},
    ]))
    asyncio.run(db["applications"].insert_one({"_id": "app1", "user": "a"}))
    asyncio.run(db["token_usage"].insert_many([
        {"user": "a", "total_tokens": 100}, {"user": "b", "total_tokens": 50},
    ]))


def test_compute_admin_stats_aggregates():
    db = AsyncMongoMockClient()["test"]
    _seed(db)
    s = asyncio.run(compute_admin_stats(db))
    assert s.total_users == 3           # a, b, c
    assert s.active_7d == 2             # a(0), b(5)
    assert s.active_30d == 3            # a, b, c
    assert s.total_searches == 2
    assert s.total_analyzed == 2        # 只算 done
    assert s.total_applications == 1
    assert s.tokens == 150 and s.llm_calls == 2
    assert len(s.daily_active) == 30    # 連續 30 天
    assert s.daily_active[-1].day == _day(0) and s.daily_active[-1].users == 1
    assert s.daily_active[0].day == _day(29)


def test_compute_admin_stats_empty():
    db = AsyncMongoMockClient()["test"]
    s = asyncio.run(compute_admin_stats(db))
    assert s.total_users == 0 and s.active_7d == 0 and s.tokens == 0
    assert len(s.daily_active) == 30 and all(d.users == 0 for d in s.daily_active)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_admin_stats.py -q`
Expected: FAIL（`job_tracker.services.admin_stats` 不存在）

- [ ] **Step 3: 實作 `admin_stats.py`**

建立 `backend/src/job_tracker/services/admin_stats.py`：

```python
"""admin 營運數據聚合：從既有 collection 統計使用人數/活躍/用量/每日趨勢。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from job_tracker.db.repositories import TokenUsageRepository


class DailyActive(BaseModel):
    day: str
    users: int


class AdminStats(BaseModel):
    total_users: int = 0
    active_7d: int = 0
    active_30d: int = 0
    total_searches: int = 0
    total_analyzed: int = 0
    total_applications: int = 0
    tokens: int = 0
    llm_calls: int = 0
    daily_active: list[DailyActive] = []


async def compute_admin_stats(db) -> AdminStats:
    today = datetime.now(UTC).date()
    cutoff_7 = (today - timedelta(days=6)).isoformat()
    cutoff_30 = (today - timedelta(days=29)).isoformat()

    users_all: set[str] = set()
    users_7: set[str] = set()
    users_30: set[str] = set()
    by_day: dict[str, set[str]] = {}
    async for d in db["daily_usage"].find({}):
        u = d.get("user")
        day = d.get("day")
        if not u or not day:
            continue
        users_all.add(u)
        if day >= cutoff_7:
            users_7.add(u)
        if day >= cutoff_30:
            users_30.add(u)
            by_day.setdefault(day, set()).add(u)

    total_searches = await db["searches"].count_documents({})
    total_analyzed = await db["matches"].count_documents({"status": "done"})
    total_applications = await db["applications"].count_documents({})
    tok = await TokenUsageRepository(db).summary()

    daily = [
        DailyActive(
            day=(day := (today - timedelta(days=i)).isoformat()),
            users=len(by_day.get(day, set())),
        )
        for i in range(29, -1, -1)
    ]

    return AdminStats(
        total_users=len(users_all),
        active_7d=len(users_7),
        active_30d=len(users_30),
        total_searches=total_searches,
        total_analyzed=total_analyzed,
        total_applications=total_applications,
        tokens=tok.get("total_tokens", 0),
        llm_calls=tok.get("calls", 0),
        daily_active=daily,
    )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_admin_stats.py -q`
Expected: 2 個測試通過。

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/services/admin_stats.py backend/tests/test_admin_stats.py
git commit -m "feat(online): admin_stats 營運數據聚合"
```

---

### Task 2: 後端端點 `GET /usage/admin-stats`

**Files:**
- Modify: `backend/src/job_tracker/api/deps.py`（加 `get_database`）
- Modify: `backend/src/job_tracker/api/routers/usage.py`（加端點）
- Test: `backend/tests/test_admin_stats_api.py`

**Interfaces:**
- Consumes: `compute_admin_stats`（Task 1）、`auth.is_admin`、`deps.current_user`、`deps.get_database`。
- Produces: `GET /usage/admin-stats`（回 `AdminStats.model_dump()`）；`deps.get_database() -> Motor db`。

- [ ] **Step 1: 寫失敗測試**

建立 `backend/tests/test_admin_stats_api.py`：

```python
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.api.routers import usage as usage_router
from job_tracker.main import app


def test_admin_stats_ok_for_admin_in_dev():
    db = AsyncMongoMockClient()["test"]
    app.dependency_overrides[deps.get_database] = lambda: db
    try:
        # dev 模式 → dev@local 視為 admin
        resp = TestClient(app).get("/api/usage/admin-stats")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert {"total_users", "active_7d", "daily_active", "tokens"} <= set(body)
    assert len(body["daily_active"]) == 30


def test_admin_stats_forbidden_for_non_admin(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    monkeypatch.setattr(usage_router, "is_admin", lambda user: False)
    app.dependency_overrides[deps.get_database] = lambda: db
    try:
        resp = TestClient(app).get("/api/usage/admin-stats")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 403
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_admin_stats_api.py -q`
Expected: FAIL（404）

- [ ] **Step 3: 加 `get_database` 依賴**

在 `backend/src/job_tracker/api/deps.py`（已 `from job_tracker.db import get_db`）加入一個依賴函式（放其他 `get_*_repo` 附近）：

```python
def get_database():
    return get_db()
```

若 `deps.py` 有 `__all__`，把 `"get_database"` 加入。

- [ ] **Step 4: 加端點**

在 `backend/src/job_tracker/api/routers/usage.py`：import 區加 `from job_tracker.api.deps import get_database` 與 `from job_tracker.services.admin_stats import compute_admin_stats`（`is_admin`、`current_user` 已 import）。在 `global_usage` 之後加：

```python
@router.get("/admin-stats")
async def admin_stats(
    user: str = Depends(current_user),
    db=Depends(get_database),
) -> dict:
    """全站營運數據（使用人數/活躍/用量/每日趨勢）。僅 admin。"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="僅管理者可檢視")
    stats = await compute_admin_stats(db)
    return stats.model_dump()
```

- [ ] **Step 5: 跑測試確認通過（含後端全套）**

Run: `cd backend && uv run pytest -q`
Expected: 既有全綠 + 2 新測試通過。

- [ ] **Step 6: Commit**

```bash
git add backend/src/job_tracker/api/deps.py backend/src/job_tracker/api/routers/usage.py backend/tests/test_admin_stats_api.py
git commit -m "feat(online): GET /usage/admin-stats（admin-gated）"
```

---

### Task 3: 前端營運數據頁 + 路由 + admin nav

**Files:**
- Modify: `frontend/src/api/client.ts`（`AdminStats` 型別 + `adminStats()`）
- Create: `frontend/src/pages/AdminStats.tsx`
- Modify: `frontend/src/main.tsx`（`/admin` 路由）
- Modify: `frontend/src/App.tsx`（nav 依 `quota.is_admin`）

**Interfaces:**
- Consumes: `api.adminStats`、`api.quota`（既有）。

- [ ] **Step 1: api client 型別與呼叫**

在 `frontend/src/api/client.ts` 的 `api` 物件加一個方法（與 `quota`/`usage` 那些同層），並在檔案適當處加型別：

```typescript
export interface DailyActive { day: string; users: number }
export interface AdminStats {
  total_users: number;
  active_7d: number;
  active_30d: number;
  total_searches: number;
  total_analyzed: number;
  total_applications: number;
  tokens: number;
  llm_calls: number;
  daily_active: DailyActive[];
}
```

在 `api` 物件內加（與 `global`/`quota` 那些 request 同風格；沿用該檔既有的 `request<T>(path)` helper）：

```typescript
  adminStats: () => request<AdminStats>("/usage/admin-stats"),
```

- [ ] **Step 2: 建立 `AdminStats.tsx`**

建立 `frontend/src/pages/AdminStats.tsx`（沿用線上前端既有的 `jt-panel`/`jt-eyebrow` 樣式與 Mantine；純 CSS 長條）：

```tsx
import { Alert, Box, Group, Loader, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api, type AdminStats as Stats } from "../api/client";

function Tile({ label, value }: { label: string; value: number }) {
  return (
    <div className="jt-panel" style={{ padding: 16 }}>
      <Text fz="xs" c="dimmed">{label}</Text>
      <Text fw={700} fz={26} c="var(--jt-text)" ff="var(--mantine-font-family-monospace)">
        {value.toLocaleString()}
      </Text>
    </div>
  );
}

export function AdminStats() {
  const quota = useQuery({ queryKey: ["quota"], queryFn: api.quota });
  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-stats"],
    queryFn: api.adminStats,
    enabled: !!quota.data?.is_admin,
  });

  if (quota.data && !quota.data.is_admin) {
    return (
      <Box p={{ base: "lg", md: 40 }} maw={1180} mx="auto">
        <Alert color="red">僅管理者可檢視此頁。</Alert>
      </Box>
    );
  }
  if (isLoading || !quota.data) return <Box p={40}><Loader /></Box>;
  if (isError || !data) return <Box p={40}><Alert color="red">數據載入失敗。</Alert></Box>;

  const s: Stats = data;
  const maxUsers = s.daily_active.reduce((m, d) => Math.max(m, d.users), 0);

  return (
    <Box p={{ base: "lg", md: 40 }} maw={1180} mx="auto">
      <span className="jt-eyebrow">營運數據</span>
      <Title order={1} fz={{ base: 26, md: 32 }} fw={700} lts="-0.02em" mb="lg">營運數據</Title>

      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing={12} mb={28}>
        <Tile label="總使用人數" value={s.total_users} />
        <Tile label="近 7 天活躍" value={s.active_7d} />
        <Tile label="近 30 天活躍" value={s.active_30d} />
        <Tile label="總搜尋數" value={s.total_searches} />
        <Tile label="總分析數" value={s.total_analyzed} />
        <Tile label="總投遞數" value={s.total_applications} />
        <Tile label="Tokens" value={s.tokens} />
        <Tile label="LLM 呼叫" value={s.llm_calls} />
      </SimpleGrid>

      <div className="jt-panel">
        <div className="jt-panel-body">
          <Text fw={600} fz="sm" mb="md">近 30 天每日活躍用戶</Text>
          <Stack gap={4}>
            {s.daily_active.map((d) => (
              <Group key={d.day} gap="sm" wrap="nowrap" align="center">
                <Text fz={11} c="dimmed" w={72} ta="right" style={{ flexShrink: 0 }}>
                  {d.day.slice(5)}
                </Text>
                <Box style={{ flex: 1, background: "var(--jt-border)", borderRadius: 4, overflow: "hidden" }}>
                  <Box style={{
                    width: `${maxUsers > 0 ? Math.max((d.users / maxUsers) * 100, d.users > 0 ? 4 : 0) : 0}%`,
                    height: 16, background: "var(--jt-teal)", borderRadius: 4, transition: "width 300ms",
                  }} />
                </Box>
                <Text fz={11} ff="var(--mantine-font-family-monospace)" w={32} style={{ flexShrink: 0 }}>
                  {d.users}
                </Text>
              </Group>
            ))}
          </Stack>
        </div>
      </div>
    </Box>
  );
}
```

（`--jt-text`/`--jt-border`/`--jt-teal` 為既有 CSS 變數，見 global.css / 其他頁沿用；若某個變數名不存在，用鄰近頁面實際採用的 token 名替換。）

- [ ] **Step 3: main.tsx 加路由**

在 `frontend/src/main.tsx`：加 lazy import 與路由（放 GatedShell 下、與 `/applications` 並列）：

```tsx
const AdminStats = lazy(() => import("./pages/AdminStats").then((m) => ({ default: m.AdminStats })));
```

```tsx
            <Route path="/applications" element={<Applications />} />
            <Route path="/admin" element={<AdminStats />} />
```

- [ ] **Step 4: App.tsx nav 依 admin 顯示**

在 `frontend/src/App.tsx` 的 `GatedLayout`：加 quota query 並在 `quota.is_admin` 時把「營運數據」加進 nav。於 `GatedLayout` 內（`NAV.map` 之前）加：

```tsx
  const { data: quota } = useQuery({ queryKey: ["quota"], queryFn: api.quota });
  const nav = quota?.is_admin
    ? [...NAV, { to: "/admin", label: "營運數據", tag: "06" }]
    : NAV;
```

把 `{NAV.map((item) => (` 改為 `{nav.map((item) => (`。（`useQuery`、`api` 於此檔已 import；若無則補 `import { useQuery } from "@tanstack/react-query";` 與 `import { api } from "./api/client";`——依現況。）

- [ ] **Step 5: 前端建置**

Run: `cd frontend && npm run build`
Expected: build 成功、無型別錯誤。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/AdminStats.tsx frontend/src/main.tsx frontend/src/App.tsx
git commit -m "feat(online): admin 營運數據頁 + /admin 路由 + admin nav"
```

---

## Self-Review

**1. Spec coverage：** 聚合服務（Task 1，含 distinct/活躍窗/done/趨勢補 0）、admin-gated 端點（Task 2，200/403）、前端頁+路由+條件 nav（Task 3）全覆蓋。資料來源與定義（total_users/active/analyzed/tokens/llm_calls/daily_active）與 spec 一致；成本不做（spec 已改）。非目標（個人明細、事件追蹤、留言板）遵守。

**2. Placeholder scan：** 無 TBD/TODO；每步含完整程式碼；`AdminStats.tsx` 有一處示意元素已附「修正」明確改法（無殘留 `Stack-ish`）。

**3. Type/名稱一致性：** `AdminStats`/`DailyActive` 欄位（total_users/active_7d/active_30d/total_searches/total_analyzed/total_applications/tokens/llm_calls/daily_active）在後端 model、前端型別、測試、頁面間一致；`compute_admin_stats(db)`、`get_database`、`adminStats()`、路由 `/admin`、nav tag "06" 一致；後端測試用 `deps.get_database` override 與 `usage_router.is_admin` monkeypatch 對應端點實作。
