"""jobs 路由：比對 / 客製化 / 開投遞頁 / 談判 / 搜尋 / 推薦 / 職缺詳情 / 公司評價。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ... import config, jobfetch, match, negotiate, pipeline, research, store, tailor, watch
from ...models import OfferDetail
from ..deps import get_db_path
from .. import apply, runner

logger = logging.getLogger("career_sentinel.web")

router = APIRouter()


class _MatchReq(BaseModel):
    job_url: str


class _NegotiateReq(BaseModel):
    code: str


@router.post("/api/match")
def match_job(req: _MatchReq, db_path: str = Depends(get_db_path)) -> dict:
    conn = store.connect(db_path)
    try:
        code = jobfetch.extract_job_code(req.job_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    state = store.load_resume(conn)
    if not state.resume_text.strip():
        raise HTTPException(status_code=400, detail="請先上傳履歷")
    try:
        jd = jobfetch.fetch_job_detail(code)
    except Exception:
        raise HTTPException(status_code=502, detail="抓取職缺失敗，請確認網址")
    try:
        result = match.match(state.resume_text, store.load_preferences(conn).target_title or "（未指定）", jd)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="比對失敗，請重試")
    return {
        "title": jd.title, "company": jd.company, "salary": jd.salary,
        "score": result.score, "reasons": result.reasons, "gaps": result.gaps,
    }


@router.post("/api/tailor")
def tailor_job(req: _MatchReq, db_path: str = Depends(get_db_path)) -> dict:
    conn = store.connect(db_path)
    if not req.job_url.strip():
        raise HTTPException(status_code=400, detail="請提供職缺網址")
    try:
        code = jobfetch.extract_job_code(req.job_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    state = store.load_resume(conn)
    if not state.resume_text.strip():
        raise HTTPException(status_code=400, detail="請先上傳履歷")
    try:
        jd = jobfetch.fetch_job_detail(code)
    except Exception:
        raise HTTPException(status_code=502, detail="抓取職缺失敗，請確認網址")
    try:
        result = tailor.tailor_application(state.resume_text, store.load_preferences(conn).target_title or "（未指定）", jd)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="生成失敗，請重試")
    return result.model_dump()


@router.post("/api/apply/open")
def apply_open(req: _MatchReq) -> dict:
    url = req.job_url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="請提供職缺網址")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="職缺網址格式不正確")
    if not runner.try_begin_browser():
        raise HTTPException(status_code=409, detail="瀏覽器忙碌中（可能正在抓取），請稍候再試")
    try:
        ok = apply.open_job_page(url)
    except Exception:
        raise HTTPException(status_code=500, detail="開啟失敗，請重試")
    finally:
        runner.end_browser()
    if not ok:
        raise HTTPException(status_code=500, detail="找不到 Google Chrome，請確認已安裝")
    return {"status": "opened"}


@router.post("/api/negotiate")
def negotiate_offer_ep(req: _NegotiateReq, db_path: str = Depends(get_db_path)) -> dict:
    conn = store.connect(db_path)
    tj = store.get_tracked_job(conn, req.code)
    if tj is None or tj.state != "offer" or not tj.offer_json:
        raise HTTPException(status_code=400, detail="此職缺沒有 offer 明細可談判")
    offer = OfferDetail.model_validate_json(tj.offer_json)
    others = []
    for pj in pipeline.build_pipeline(conn):
        if pj.state == "offer" and pj.code != req.code and pj.offer is not None:
            others.append({"company": pj.company, "title": pj.title,
                           "salary_year": pj.offer.salary_year, "salary_month": pj.offer.salary_month})
    expected = store.load_preferences(conn).expected_salary
    try:
        result = negotiate.negotiate_offer(offer, tj.company, tj.title, others, expected)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="產生談判建議失敗，請重試")
    return result.model_dump()


@router.get("/api/search")
def search(kw: str = "", page: int = 1, db_path: str = Depends(get_db_path)) -> dict:
    from ...scraper.search import fetch_search
    if not kw.strip():
        raise HTTPException(status_code=400, detail="請輸入搜尋關鍵字")
    page = max(1, page)
    try:
        jobs = fetch_search(kw.strip(), page=page)
    except Exception:
        raise HTTPException(status_code=502, detail="搜尋失敗，請重試")
    settings = store.load_settings(store.connect(db_path))
    return {
        "page": page,
        "has_more": len(jobs) >= 20,  # 滿頁視為還有下一頁
        "jobs": [
            {
                "code": j.code, "url": j.url, "title": j.title,
                "company": j.company, "salary": j.salary,
                "is_watched": watch.is_watched(j.company, j.title, settings),
            }
            for j in jobs
        ],
    }


@router.get("/api/recommend")
def recommend(db_path: str = Depends(get_db_path)) -> dict:
    from ...scraper.recommend import recommend_session
    if not runner.try_begin_browser():
        raise HTTPException(status_code=409, detail="瀏覽器忙碌中（可能正在抓取），請稍候再試")
    try:
        jobs = recommend_session()
    except Exception:
        logger.exception("recommend fetch failed")
        raise HTTPException(status_code=502, detail="拉取推薦失敗，請重試")
    finally:
        runner.end_browser()
    if jobs is None:
        raise HTTPException(status_code=409, detail="尚未登入，請先在終端機執行：career-sentinel login")
    settings = store.load_settings(store.connect(db_path))
    return {
        "jobs": [
            {
                "code": j.code, "url": j.url, "title": j.title,
                "company": j.company, "salary": j.salary,
                "is_watched": watch.is_watched(j.company, j.title, settings),
            }
            for j in jobs
        ]
    }


@router.get("/api/job")
def job_by_url(url: str = "", db_path: str = Depends(get_db_path)) -> dict:
    if not url.strip():
        raise HTTPException(status_code=400, detail="請提供職缺網址")
    try:
        code = jobfetch.extract_job_code(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        jd = jobfetch.fetch_job_detail(code)
    except Exception:
        raise HTTPException(status_code=502, detail="抓取職缺失敗，請確認網址")
    settings = store.load_settings(store.connect(db_path))
    return {
        "code": code, "url": url, "title": jd.title, "company": jd.company,
        "salary": jd.salary, "is_watched": watch.is_watched(jd.company, jd.title, settings),
    }


@router.get("/api/research")
def research_get(company: str = "", force: int = 0, db_path: str = Depends(get_db_path)) -> dict:
    name = company.strip()
    if not name:
        raise HTTPException(status_code=400, detail="請提供公司名稱")
    if not config.llm_provider():
        raise HTTPException(status_code=400, detail="請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")
    conn2 = store.connect(db_path)
    cached = store.load_research(conn2, name)
    if cached and not force and research.is_fresh(cached):
        return {**cached.model_dump(), "cached": True}
    try:
        r = research.research_company(name)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("公司評價查詢失敗：%s", name)
        raise HTTPException(status_code=502, detail="查詢失敗，請重試")
    store.save_research(conn2, r)
    return {**r.model_dump(), "cached": False}
