import json
from pathlib import Path

import httpx

from job_tracker import crawler
from job_tracker.crawler import (
    _format_salary,
    crawl_job_details,
    crawl_jobs,
    fetch_job_detail,
    parse_job_detail,
    parse_jobs,
)

FIXTURE = Path(__file__).parent / "fixtures" / "104_search.json"
DETAIL_FIXTURE = Path(__file__).parent / "fixtures" / "104_detail.json"


def load_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def load_detail_payload() -> dict:
    return json.loads(DETAIL_FIXTURE.read_text(encoding="utf-8"))


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


def test_format_salary_negotiable():
    assert _format_salary(0, 0) == "面議"


def test_format_salary_range():
    assert _format_salary(48000, 75000) == "48,000~75,000"


def test_format_salary_upper_unbounded():
    # 104 用 9999999 表示「以上」（無上限），不該顯示成 60,000~9,999,999
    assert _format_salary(60000, 9999999) == "60,000 以上"


def test_parse_jobs_extracts_short_code():
    # 詳情 API 用的是 url 末段短碼，需從 link.job 取出
    job = parse_jobs(load_payload())[0]
    assert job.code == "8rl43"


def test_parse_job_detail_extracts_fields():
    detail = parse_job_detail(load_detail_payload())
    assert "Job Description" in detail.description
    assert detail.salary == "待遇面議"
    assert detail.location == "台北市大安區"
    assert detail.work_exp == "不拘"
    assert detail.education == "專科、大學、碩士"
    assert "Linux" in detail.specialties
    assert "C++" in detail.specialties


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


async def test_fetch_job_detail_uses_job_specific_referer():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["referer"] = request.headers.get("referer")
        captured["url"] = str(request.url)
        return httpx.Response(200, json=load_detail_payload())

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        detail = await fetch_job_detail("8rl43", client=client)

    # 詳情 API 需帶該職缺自己的 Referer 才不會 403
    assert captured["referer"] == "https://www.104.com.tw/job/8rl43"
    assert "8rl43" in captured["url"]
    assert detail.salary == "待遇面議"


async def test_crawl_job_details_throttles_between_requests(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(crawler.asyncio, "sleep", fake_sleep)
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=load_detail_payload())
    )

    async with httpx.AsyncClient(transport=transport) as client:
        details = await crawl_job_details(
            ["aaa", "bbb", "ccc"], client=client, min_delay=2.0, max_delay=5.0
        )

    assert len(details) == 3
    # 3 個請求 → 之間延遲 2 次（首個請求前不延遲）
    assert len(sleeps) == 2
    assert all(2.0 <= s <= 5.0 for s in sleeps)
