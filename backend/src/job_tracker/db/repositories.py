"""職缺資料存取（MongoDB）。

文件結構：以 job_id 為 _id，存 Job 欄位；詳情存在 `detail` 子文件。
"""

from motor.motor_asyncio import AsyncIOMotorDatabase

from job_tracker.schemas import Job, JobDetail, JobMatch


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

    async def set_match(self, job_id: str, match: JobMatch) -> None:
        """存契合度分析結果（不含 job 本身，job 已在文件中）。"""
        await self._col.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "match": {
                        "score": match.score,
                        "reasons": match.reasons,
                        "gaps": match.gaps,
                        "requires_external_apply": match.requires_external_apply,
                    }
                }
            },
        )

    async def list_matches(self) -> list[JobMatch]:
        """回傳已分析的職缺，依契合度由高到低排序。"""
        matches = [
            JobMatch(job=Job(**doc), **doc["match"])
            async for doc in self._col.find({"match": {"$exists": True}})
        ]
        return sorted(matches, key=lambda m: m.score, reverse=True)
