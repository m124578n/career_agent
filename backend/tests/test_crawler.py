import json
from pathlib import Path

import httpx

from job_tracker.crawler import crawl_jobs, parse_jobs

FIXTURE = Path(__file__).parent / "fixtures" / "104_search.json"


def load_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_jobs_returns_all_jobs():
    jobs = parse_jobs(load_payload())
    assert len(jobs) == 2


def test_parse_jobs_maps_core_fields():
    job = parse_jobs(load_payload())[0]
    assert job.job_id == "14724003"
    # jobName 有尾端空白，需 strip
    assert job.title == "R0007868: (Sr.) Applied AI Module Engineer"
    assert job.company.startswith("Trend Micro")
    assert job.url == "https://www.104.com.tw/job/8rl43"


def test_parse_jobs_formats_negotiable_salary():
    # salaryLow/High 皆 0 → 面議
    job = parse_jobs(load_payload())[0]
    assert job.salary == "面議"


async def test_crawl_jobs_sends_referer_and_parses():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["referer"] = request.headers.get("referer")
        captured["keyword"] = request.url.params.get("keyword")
        return httpx.Response(200, json=load_payload())

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        jobs = await crawl_jobs("python", client=client)

    # 沒帶 Referer 會被 104 擋（403），所以必須送
    assert captured["referer"] == "https://www.104.com.tw/jobs/search/"
    assert captured["keyword"] == "python"
    assert len(jobs) == 2
    assert jobs[0].job_id == "14724003"
