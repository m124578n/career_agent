"""職缺資料存取（MongoDB）。

文件結構：以 job_id 為 _id，存 Job 欄位；詳情存在 `detail` 子文件。
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase

from job_tracker.schemas import (
    Application,
    ApplicationEvent,
    ApplicationStatus,
    CrawlTask,
    Job,
    JobDetail,
    JobMatch,
    OfferInfo,
    ResumeTarget,
    SearchRun,
)


class JobRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["jobs"]

    async def upsert_job(self, job: Job) -> None:
        """以 job_id 為主鍵 upsert，重複爬到同職缺不會重複。"""
        doc = job.model_dump(mode="json")
        await self._col.update_one(
            {"_id": job.job_id}, {"$set": doc}, upsert=True
        )

    async def get_job(self, job_id: str) -> Job | None:
        doc = await self._col.find_one({"_id": job_id})
        return Job(**doc) if doc else None

    async def list_jobs(self) -> list[Job]:
        return [Job(**doc) async for doc in self._col.find()]

    async def set_detail(self, job_id: str, detail: JobDetail) -> None:
        await self._col.update_one(
            {"_id": job_id},
            {"$set": {"detail": detail.model_dump(mode="json")}},
        )

    async def get_detail(self, job_id: str) -> JobDetail | None:
        doc = await self._col.find_one(
            {"_id": job_id}, {"detail": 1}
        )
        if not doc or "detail" not in doc:
            return None
        return JobDetail(**doc["detail"])


class MatchRepository:
    """契合度分析結果，綁定到一筆 search（_id = search_id|job_id）。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["matches"]

    async def set_match(self, search_id: str, user: str, match: JobMatch) -> None:
        doc = match.model_dump(mode="json")
        doc["search_id"] = search_id
        doc["user"] = user
        doc["job_id"] = match.job.job_id
        await self._col.update_one(
            {"_id": f"{search_id}|{match.job.job_id}"}, {"$set": doc}, upsert=True
        )

    async def list_by_search(self, search_id: str) -> list[JobMatch]:
        matches = [
            JobMatch(**doc) async for doc in self._col.find({"search_id": search_id})
        ]
        return sorted(matches, key=lambda m: m.score, reverse=True)

    async def get_match(self, search_id: str, job_id: str) -> JobMatch | None:
        doc = await self._col.find_one({"_id": f"{search_id}|{job_id}"})
        return JobMatch(**doc) if doc else None

    async def set_cover_letter(self, search_id: str, job_id: str, text: str) -> None:
        await self._col.update_one(
            {"_id": f"{search_id}|{job_id}"}, {"$set": {"cover_letter": text}}
        )

    async def add_candidate(self, search_id, user, job, relevant) -> None:
        _id = f"{search_id}|{job.job_id}"
        if await self._col.find_one({"_id": _id}):
            return  # 已存在不覆蓋（重複爬到同職缺）
        doc = JobMatch(job=job, status="candidate", relevant=relevant).model_dump(mode="json")
        doc.update({"_id": _id, "search_id": search_id, "user": user, "job_id": job.job_id})
        await self._col.insert_one(doc)

    async def set_pending(self, search_id, job_ids) -> None:
        await self._col.update_many(
            {"search_id": search_id, "job_id": {"$in": list(job_ids)}},
            {"$set": {"status": "pending"}},
        )

    async def set_result(self, search_id, job_id, analysis) -> None:
        await self._col.update_one(
            {"_id": f"{search_id}|{job_id}"},
            {"$set": {
                "score": analysis.score,
                "reasons": analysis.reasons,
                "gaps": analysis.gaps,
                "benefits": analysis.benefits,
                "requires_external_apply": analysis.requires_external_apply,
                "status": "done",
            }},
        )

    async def set_failed(self, search_id, job_id) -> None:
        await self._col.update_one(
            {"_id": f"{search_id}|{job_id}"}, {"$set": {"status": "failed"}}
        )


class SearchRepository:
    """搜尋歷史（每次「爬取並分析」一筆）。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["searches"]
        self._matches = db["matches"]

    async def create(self, user, keyword, target, area=None) -> SearchRun:
        run = SearchRun(search_id=uuid4().hex, user=user, keyword=keyword,
                        target=target, area=area, crawl_status="queued")
        doc = run.model_dump(mode="json")
        doc["_id"] = run.search_id
        await self._col.insert_one(doc)
        return run

    async def get(self, search_id: str) -> SearchRun | None:
        doc = await self._col.find_one({"_id": search_id})
        return SearchRun(**doc) if doc else None

    async def list(self, user: str) -> list[SearchRun]:
        cur = self._col.find({"user": user}).sort("created_at", -1)
        return [SearchRun(**doc) async for doc in cur]

    async def set_crawl_status(self, search_id: str, status: str) -> None:
        await self._col.update_one({"_id": search_id},
                                   {"$set": {"crawl_status": status}})

    async def advance_page(self, search_id, next_page, count_delta) -> None:
        await self._col.update_one(
            {"_id": search_id},
            {"$set": {"next_page": next_page}, "$inc": {"count": count_delta}},
        )

    async def delete(self, search_id: str) -> None:
        await self._col.delete_one({"_id": search_id})
        await self._matches.delete_many({"search_id": search_id})


class QuotaRepository:
    """每位使用者每日 LLM 呼叫次數（防止濫用）。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["daily_usage"]

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).date().isoformat()

    async def used_today(self, user: str) -> int:
        doc = await self._col.find_one({"_id": f"{user}|{self._today()}"})
        return doc["count"] if doc else 0

    async def add(self, user: str, n: int) -> None:
        day = self._today()
        await self._col.update_one(
            {"_id": f"{user}|{day}"},
            {"$inc": {"count": n}, "$setOnInsert": {"user": user, "day": day}},
            upsert=True,
        )


class TokenUsageRepository:
    """LLM token 用量記錄（每次呼叫一筆）。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["token_usage"]

    async def record(self, usage: dict) -> None:
        await self._col.insert_one(dict(usage))

    async def summary(self, user: str | None = None) -> dict:
        """彙總用量。user=None → 全站；否則只算該使用者。"""
        query = {} if user is None else {"user": user}
        calls = 0
        inp = out = total = 0
        by_model: dict[str, int] = {}
        async for d in self._col.find(query):
            calls += 1
            inp += d.get("input_tokens", 0)
            out += d.get("output_tokens", 0)
            t = d.get("total_tokens", 0)
            total += t
            by_model[d.get("model", "?")] = by_model.get(d.get("model", "?"), 0) + t
        return {
            "calls": calls,
            "input_tokens": inp,
            "output_tokens": out,
            "total_tokens": total,
            "by_model": by_model,
        }


class ApplicationRepository:
    """求職追蹤清單（以 user|job_id 去重）。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["applications"]

    @staticmethod
    def _id(user: str, job_id: str) -> str:
        return f"{user}|{job_id}"

    async def add(self, app: Application) -> Application:
        _id = self._id(app.user, app.job_id)
        existing = await self._col.find_one({"_id": _id})
        if existing:
            return Application(**existing)  # 去重：已在追蹤就回現有
        doc = app.model_dump(mode="json")
        doc["_id"] = _id
        await self._col.insert_one(doc)
        return app

    async def list(self, user: str) -> list[Application]:
        cur = self._col.find({"user": user}).sort("created_at", -1)
        return [Application(**doc) async for doc in cur]

    async def get(self, user: str, job_id: str) -> Application | None:
        doc = await self._col.find_one({"_id": self._id(user, job_id)})
        return Application(**doc) if doc else None

    async def set_status(
        self, user: str, job_id: str, status: ApplicationStatus
    ) -> Application | None:
        ev = ApplicationEvent(type="status", note=f"→ {status.value}")
        now = ev.ts
        res = await self._col.update_one(
            {"_id": self._id(user, job_id)},
            {
                "$set": {"status": status.value, "updated_at": now.isoformat()},
                "$push": {"events": ev.model_dump(mode="json")},
            },
        )
        if res.matched_count == 0:
            return None
        return await self.get(user, job_id)

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

    async def remove(self, user: str, job_id: str) -> None:
        await self._col.delete_one({"_id": self._id(user, job_id)})


class CrawlTaskRepository:
    """交給本機 agent 代打 104 的任務隊列。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["crawl_tasks"]
        self._searches = db["searches"]

    async def enqueue(self, task: CrawlTask) -> CrawlTask:
        doc = task.model_dump(mode="json")
        doc["_id"] = task.task_id
        await self._col.insert_one(doc)
        return task

    async def claim(self) -> CrawlTask | None:
        """原子認領一個 pending 任務（pending→claimed）。多 agent 也安全。"""
        doc = await self._col.find_one_and_update(
            {"status": "pending"},
            {"$set": {"status": "claimed",
                      "claimed_at": datetime.now(UTC).isoformat()}},
            sort=[("created_at", 1)],
            return_document=True,
        )
        return CrawlTask(**doc) if doc else None

    async def get(self, task_id: str) -> CrawlTask | None:
        doc = await self._col.find_one({"_id": task_id})
        return CrawlTask(**doc) if doc else None

    async def complete(self, task_id: str, raw_json: dict) -> CrawlTask | None:
        doc = await self._col.find_one_and_update(
            {"_id": task_id, "status": "claimed"},
            {"$set": {"status": "done", "raw_json": raw_json,
                      "completed_at": datetime.now(UTC).isoformat()}},
            return_document=True,
        )
        return CrawlTask(**doc) if doc else None

    async def fail(self, task_id: str, error: str) -> CrawlTask | None:
        doc = await self._col.find_one_and_update(
            {"_id": task_id, "status": "claimed"},
            {"$set": {"status": "failed", "error": error,
                      "completed_at": datetime.now(UTC).isoformat()}},
            return_document=True,
        )
        return CrawlTask(**doc) if doc else None

    async def reap(self, pending_ttl_sec: int, claimed_ttl_sec: int) -> None:
        now = datetime.now(UTC)
        pending_cutoff = (now - timedelta(seconds=pending_ttl_sec)).isoformat()
        claimed_cutoff = (now - timedelta(seconds=claimed_ttl_sec)).isoformat()
        # Collect search_ids of search-type tasks about to expire
        expiring_filter = {
            "type": "search",
            "status": "pending",
            "created_at": {"$lt": pending_cutoff},
        }
        search_ids = [
            doc["search_id"]
            async for doc in self._col.find(expiring_filter, {"search_id": 1})
        ]
        await self._col.update_many(
            {"status": "pending", "created_at": {"$lt": pending_cutoff}},
            {"$set": {"status": "expired"}},
        )
        # Propagate expired status to owning SearchRun documents
        if search_ids:
            await self._searches.update_many(
                {"_id": {"$in": search_ids}},
                {"$set": {"crawl_status": "expired"}},
            )
        await self._col.update_many(
            {"status": "claimed", "claimed_at": {"$lt": claimed_cutoff}},
            {"$set": {"status": "pending", "claimed_at": None}},
        )


class AgentStatusRepository:
    """記錄本機 agent 最近一次心跳，供前端判斷在線/離線。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["agent_status"]

    async def touch(self) -> None:
        await self._col.update_one(
            {"_id": "agent"},
            {"$set": {"last_seen": datetime.now(UTC).isoformat()}},
            upsert=True,
        )

    async def last_seen(self) -> datetime | None:
        doc = await self._col.find_one({"_id": "agent"})
        if not doc or "last_seen" not in doc:
            return None
        return datetime.fromisoformat(doc["last_seen"])

    async def is_online(self, window_sec: int) -> bool:
        seen = await self.last_seen()
        if seen is None:
            return False
        return (datetime.now(UTC) - seen).total_seconds() <= window_sec
