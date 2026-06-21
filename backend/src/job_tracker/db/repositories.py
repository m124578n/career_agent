"""職缺資料存取（MongoDB）。

文件結構：以 job_id 為 _id，存 Job 欄位；詳情存在 `detail` 子文件。
"""

from motor.motor_asyncio import AsyncIOMotorDatabase

from job_tracker.schemas import Job, JobDetail


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
