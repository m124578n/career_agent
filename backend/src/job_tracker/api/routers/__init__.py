"""把各 router 匯整成一個 api_router，給 main.py 掛載。"""

from fastapi import APIRouter

from job_tracker.api.routers import applications, jobs, resumes, usage

api_router = APIRouter(prefix="/api")
api_router.include_router(resumes.router)
api_router.include_router(jobs.router)
api_router.include_router(applications.router)
api_router.include_router(usage.router)
