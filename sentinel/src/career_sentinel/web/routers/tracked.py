"""tracked 路由：追蹤管道狀態 / offer / 面試紀錄 / 面試邀約摺疊。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ... import store
from ...models import InterviewNote, OfferDetail
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
                "match": None, "tailor": None, "offer": None, "interviews": []}
    return {
        "code": tj.code, "found": True, "state": tj.state, "match_score": tj.match_score,
        "match": json.loads(tj.match_json) if tj.match_json else None,
        "tailor": json.loads(tj.tailor_json) if tj.tailor_json else None,
        "offer": json.loads(tj.offer_json) if tj.offer_json else None,
        "interviews": json.loads(tj.interviews_json) if tj.interviews_json else [],
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
