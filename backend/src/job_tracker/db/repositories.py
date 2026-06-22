"""職缺資料存取（MongoDB）。

文件結構：以 job_id 為 _id，存 Job 欄位；詳情存在 `detail` 子文件。
"""

from datetime import UTC, datetime
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase

from job_tracker.schemas import Job, JobDetail, JobMatch, ResumeTarget, SearchRun


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


class SearchRepository:
    """搜尋歷史（每次「爬取並分析」一筆）。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["searches"]
        self._matches = db["matches"]

    async def create(self, user: str, keyword: str, target: ResumeTarget) -> SearchRun:
        run = SearchRun(search_id=uuid4().hex, user=user, keyword=keyword, target=target)
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

    async def advance(self, search_id: str, next_offset: int, count_delta: int) -> None:
        await self._col.update_one(
            {"_id": search_id},
            {"$set": {"next_offset": next_offset}, "$inc": {"count": count_delta}},
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
