"""tracked 路由：追蹤管道狀態 / offer / 面試紀錄 / 面試邀約摺疊。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ... import interview_prep, jobfetch, store
from ...models import InterviewNote, MatchResult, OfferDetail
from ..deps import get_db_path

router = APIRouter()


class _TrackReq(BaseModel):
    code: str
    company: str = ""
    title: str = ""
    url: str = ""
    salary: str = ""
    match_score: int | None = None
    match_json: dict | None = None
    tailor_json: dict | None = None


class _InterviewKeyReq(BaseModel):
    key: str


class _InterviewsReq(BaseModel):
    notes: list[InterviewNote]


class _InterviewPrepReq(BaseModel):
    deep: bool = False


@router.post("/api/tracked")
def track_job(req: _TrackReq, db_path: str = Depends(get_db_path)) -> dict:
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="缺少職缺代碼")
    if req.tailor_json is not None:
        state_hint = "tailored"
    elif req.match_json is not None or req.match_score is not None:
        state_hint = "matched"
    else:
        state_hint = "interested"
    final = store.merge_tracked_job(
        store.connect(db_path), req.code, state=state_hint,
        match_score=req.match_score, match_json=req.match_json, tailor_json=req.tailor_json,
        company=req.company, title=req.title, url=req.url, salary=req.salary,
    )
    return {"status": "tracked", "state": final}


@router.get("/api/tracked/{code}")
def tracked_get(code: str, db_path: str = Depends(get_db_path)) -> dict:
    tj = store.get_tracked_job(store.connect(db_path), code)
    if tj is None:
        return {"code": code, "found": False, "state": "", "match_score": None,
                "match": None, "tailor": None, "offer": None, "interviews": [], "interview_prep": None}
    return {
        "code": tj.code, "found": True, "state": tj.state, "match_score": tj.match_score,
        "match": json.loads(tj.match_json) if tj.match_json else None,
        "tailor": json.loads(tj.tailor_json) if tj.tailor_json else None,
        "offer": json.loads(tj.offer_json) if tj.offer_json else None,
        "interviews": json.loads(tj.interviews_json) if tj.interviews_json else [],
        "interview_prep": json.loads(tj.interview_prep_json) if tj.interview_prep_json else None,
    }


@router.delete("/api/tracked/{code}")
def untrack_job(code: str, db_path: str = Depends(get_db_path)) -> dict:
    store.delete_tracked_job(store.connect(db_path), code)
    return {"status": "untracked"}


@router.post("/api/tracked/{code}/offer")
def tracked_set_offer(code: str, offer: OfferDetail, db_path: str = Depends(get_db_path)) -> dict:
    if not code.strip():
        raise HTTPException(status_code=400, detail="缺少職缺代碼")
    final = store.set_tracked_state(store.connect(db_path), code, "offer", offer=offer)
    return {"status": "ok", "state": final}


@router.post("/api/tracked/{code}/reject")
def tracked_set_reject(code: str, db_path: str = Depends(get_db_path)) -> dict:
    if not code.strip():
        raise HTTPException(status_code=400, detail="缺少職缺代碼")
    final = store.set_tracked_state(store.connect(db_path), code, "rejected")
    return {"status": "ok", "state": final}


@router.post("/api/tracked/{code}/reset")
def tracked_reset(code: str, db_path: str = Depends(get_db_path)) -> dict:
    if not code.strip():
        raise HTTPException(status_code=400, detail="缺少職缺代碼")
    final = store.set_tracked_state(store.connect(db_path), code, "interested")
    return {"status": "ok", "state": final}


@router.put("/api/tracked/{code}/interviews")
def set_interviews_ep(code: str, req: _InterviewsReq, db_path: str = Depends(get_db_path)) -> dict:
    if not code.strip():
        raise HTTPException(status_code=400, detail="缺少職缺代碼")
    store.set_interviews(store.connect(db_path), code, req.notes)
    return {"status": "ok", "count": len(req.notes)}


@router.post("/api/tracked/{code}/interview-prep")
def interview_prep_ep(code: str, req: _InterviewPrepReq, db_path: str = Depends(get_db_path)) -> dict:
    if not code.strip():
        raise HTTPException(status_code=400, detail="缺少職缺代碼")
    conn = store.connect(db_path)
    resume = store.load_resume(conn)
    if not resume.resume_text.strip():
        raise HTTPException(status_code=400, detail="請先上傳履歷")
    try:
        jd = jobfetch.fetch_job_detail(code)
    except Exception:
        raise HTTPException(status_code=502, detail="抓取職缺失敗，請確認職缺代碼")
    tj = store.get_tracked_job(conn, code)
    gaps: list[str] = []
    if tj is not None and tj.match_json:
        try:
            gaps = MatchResult.model_validate_json(tj.match_json).gaps
        except Exception:
            gaps = []
    prefs = store.load_preferences(conn)
    try:
        prep = interview_prep.prepare_interview(jd, resume.resume_text, gaps, prefs.target_title, deep=req.deep)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="產生面試準備失敗，請重試")
    store.set_interview_prep(conn, code, prep)
    return prep.model_dump()


@router.post("/api/interviews/dismiss")
def interviews_dismiss(req: _InterviewKeyReq, db_path: str = Depends(get_db_path)) -> dict:
    conn2 = store.connect(db_path)
    d = store.load_dismissed(conn2)
    if req.key not in d.keys:
        d.keys.append(req.key)
        store.save_dismissed(conn2, d)
    return {"ok": True}


@router.post("/api/interviews/restore")
def interviews_restore(req: _InterviewKeyReq, db_path: str = Depends(get_db_path)) -> dict:
    conn2 = store.connect(db_path)
    d = store.load_dismissed(conn2)
    if req.key in d.keys:
        d.keys.remove(req.key)
        store.save_dismissed(conn2, d)
    return {"ok": True}
