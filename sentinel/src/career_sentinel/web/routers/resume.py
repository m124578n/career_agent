"""resume 路由：上傳 / 健檢 / 從 104 匯入 / 讀取狀態。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ... import diagnosis, resume, store
from ..deps import get_db_path
from .. import runner

logger = logging.getLogger("career_sentinel.web")

router = APIRouter()


@router.post("/api/resume/upload")
async def resume_upload(file: UploadFile = File(...), db_path: str = Depends(get_db_path)) -> dict:
    data = await file.read()
    try:
        text = resume.parse_resume(file.filename or "resume", data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    conn = store.connect(db_path)
    state = store.load_resume(conn)
    state.resume_text = text
    state.source = "upload"
    store.save_resume(conn, state)
    return {"chars": len(text)}


@router.post("/api/resume/diagnose")
def resume_diagnose(db_path: str = Depends(get_db_path)) -> dict:
    conn = store.connect(db_path)
    state = store.load_resume(conn)
    if not state.resume_text.strip():
        raise HTTPException(status_code=400, detail="請先上傳履歷")
    prefs = store.load_preferences(conn)
    if not prefs.target_title.strip():
        raise HTTPException(status_code=400, detail="請先在偏好設定目標職稱")
    try:
        result = diagnosis.diagnose(state.resume_text, prefs.target_title, prefs.expected_salary)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="健檢失敗，請重試")
    state.diagnosis = result
    store.save_resume(conn, state)
    return result.model_dump()


@router.post("/api/resume/import104")
def resume_import104(db_path: str = Depends(get_db_path)) -> dict:
    from ...scraper import resume104 as r104
    if not runner.try_begin_browser():
        raise HTTPException(status_code=409, detail="瀏覽器忙碌中（可能正在抓取），請稍候再試")
    try:
        r = r104.resume104_session()
    except Exception:
        logger.exception("resume104 import failed")
        raise HTTPException(status_code=502, detail="讀取 104 履歷失敗，請重試")
    finally:
        runner.end_browser()
    if r is None:
        raise HTTPException(status_code=409, detail="尚未登入，請先在終端機執行：career-sentinel login")
    text = r104.flatten_for_diagnosis(r)
    if not text.strip():
        raise HTTPException(status_code=400, detail="104 履歷內容為空（可能未填寫），無法匯入")
    conn = store.connect(db_path)
    state = store.load_resume(conn)
    state.resume_text = text
    state.source = "104"
    store.save_resume(conn, state)
    return {"chars": len(text), "resume104": r.model_dump()}


@router.get("/api/resume")
def resume_get(db_path: str = Depends(get_db_path)) -> dict:
    state = store.load_resume(store.connect(db_path))
    return {
        "has_resume": bool(state.resume_text.strip()),
        "chars": len(state.resume_text),
        "diagnosis": state.diagnosis.model_dump() if state.diagnosis else None,
        "source": state.source,
    }
