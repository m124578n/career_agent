from __future__ import annotations

import json
import logging
from pathlib import Path

from datetime import date

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import calendar_link, chat as chatmod, company_link, config, diagnosis, diff, digest, jobfetch, llm, match, negotiate, pipeline, research, resume, store, tailor, usage as usagemod, watch
from ..models import ChatMessage, ChatState, InterviewNote, JobPreferences, OfferDetail, Settings, SuggestedUpdate, interview_key
from . import apply, runner, scheduler
from .routers import dashboard, jobs, resume, settings

logger = logging.getLogger("career_sentinel.web")


class _TrackReq(BaseModel):
    code: str
    company: str = ""
    title: str = ""
    url: str = ""
    salary: str = ""
    match_score: int | None = None
    match_json: dict | None = None
    tailor_json: dict | None = None


class _ChatReq(BaseModel):
    message: str


class _InterviewKeyReq(BaseModel):
    key: str


class _InterviewsReq(BaseModel):
    notes: list[InterviewNote]


def _chat_events(messages, system, db_path=None):
    """依 provider 產聊天事件流：foundry 走工具迴圈、openai 走既有純聊天。"""
    if config.llm_provider() == "foundry":
        yield from chatmod.stream_with_tools(messages, system=system, db_path=db_path)
    else:
        for chunk in llm.chat_stream(messages, system=system, feature="整理助手"):
            yield {"type": "text", "text": chunk}


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="career-sentinel")
    resolved_db = db_path or str(config.db_path())
    app.state.db_path = resolved_db

    def _conn():
        return store.connect(resolved_db)

    scheduler.start(lambda: store.load_settings(store.connect(resolved_db)))

    @app.post("/api/chat")
    def chat_send(req: _ChatReq):
        if not config.llm_provider():
            raise HTTPException(status_code=400, detail="請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")
        conn = _conn()
        try:
            pipe_summary = chatmod.format_pipeline_summary(pipeline.build_pipeline(conn))
        except Exception:
            pipe_summary = ""
        system = chatmod.build_system_prompt(
            store.load_resume(conn), store.load_settings(conn),
            store.load_preferences(conn), store.load_memory(conn), pipe_summary,
        )
        messages = chatmod.build_messages(store.load_chat(conn), req.message)
        settings_snapshot = store.load_settings(conn)

        def _sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        def gen():
            filt = chatmod.StreamFilter()
            clean_parts: list[str] = []
            try:
                for ev in _chat_events(messages, system, resolved_db):
                    if ev["type"] == "jobs":
                        yield _sse("jobs", {
                            "keyword": ev["keyword"],
                            "items": [
                                {
                                    "code": j.code, "url": j.url, "title": j.title,
                                    "company": j.company, "salary": j.salary,
                                    "is_watched": watch.is_watched(j.company, j.title, settings_snapshot),
                                }
                                for j in ev["items"]
                            ],
                        })
                        continue
                    out = filt.feed(ev["text"])
                    if out:
                        clean_parts.append(out)
                        yield _sse("delta", {"text": out})
                rest = filt.finish()
                if rest:
                    clean_parts.append(rest)
                    yield _sse("delta", {"text": rest})
            except Exception as exc:
                yield _sse("error", {"message": f"回覆中斷：{exc}"})
                return  # 中斷的回覆不持久化
            gconn = _conn()  # generator 可能跑在不同執行緒，sqlite 連線在此建立
            suggestions = chatmod.parse_suggestions(filt.tail())
            cards = [s for s in suggestions if s.field != "memory"]
            remembered: list[str] = []
            forgot: list[str] = []
            for s in suggestions:
                if s.field == "memory" and chatmod.apply_update(gconn, s).ok:
                    (remembered if s.op == "remember" else forgot).append(str(s.value or ""))
            if cards:
                yield _sse("suggestions", {"items": [c.model_dump() for c in cards]})
            if remembered:
                yield _sse("remembered", {"facts": remembered})
            if forgot:
                yield _sse("forgot", {"facts": forgot})
            st = store.load_chat(gconn)
            st.messages.append(ChatMessage(role="user", content=req.message))
            st.messages.append(ChatMessage(role="assistant", content="".join(clean_parts)))
            store.save_chat(gconn, st)
            chatmod.maybe_compact(gconn, st)
            chatmod.maybe_curate_memory(gconn)
            yield _sse("done", {})

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/api/chat/apply")
    def chat_apply(upd: SuggestedUpdate) -> dict:
        res = chatmod.apply_update(_conn(), upd)
        if not res.ok and res.message.startswith("不允許"):
            raise HTTPException(status_code=400, detail=res.message)
        return res.model_dump()

    @app.get("/api/chat")
    def chat_get() -> dict:
        conn2 = _conn()
        st = store.load_chat(conn2)
        mem = store.load_memory(conn2)
        return {
            "summary": st.summary,
            "messages": [m.model_dump() for m in st.messages],
            "memory": [f.model_dump() for f in mem.facts],
        }

    @app.delete("/api/chat")
    def chat_clear() -> dict:
        store.save_chat(_conn(), ChatState())
        return {"ok": True}

    @app.get("/api/export")
    def export_md() -> Response:
        conn2 = _conn()
        md = chatmod.build_export_md(
            store.load_resume(conn2), store.load_settings(conn2),
            store.load_preferences(conn2), store.load_memory(conn2),
            store.load_chat(conn2),
        )
        return Response(
            content=md,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="career-profile-{date.today().isoformat()}.md"'},
        )

    @app.post("/api/interviews/dismiss")
    def interviews_dismiss(req: _InterviewKeyReq) -> dict:
        conn2 = _conn()
        d = store.load_dismissed(conn2)
        if req.key not in d.keys:
            d.keys.append(req.key)
            store.save_dismissed(conn2, d)
        return {"ok": True}

    @app.post("/api/interviews/restore")
    def interviews_restore(req: _InterviewKeyReq) -> dict:
        conn2 = _conn()
        d = store.load_dismissed(conn2)
        if req.key in d.keys:
            d.keys.remove(req.key)
            store.save_dismissed(conn2, d)
        return {"ok": True}

    @app.delete("/api/memory/{index}")
    def memory_delete(index: int) -> dict:
        conn2 = _conn()
        mem = store.load_memory(conn2)
        if not (0 <= index < len(mem.facts)):
            raise HTTPException(status_code=404, detail="memory 不存在")
        mem.facts.pop(index)
        store.save_memory(conn2, mem)
        return {"ok": True}

    @app.post("/api/tracked")
    def track_job(req: _TrackReq) -> dict:
        if not req.code.strip():
            raise HTTPException(status_code=400, detail="缺少職缺代碼")
        if req.tailor_json is not None:
            state_hint = "tailored"
        elif req.match_json is not None or req.match_score is not None:
            state_hint = "matched"
        else:
            state_hint = "interested"
        final = store.merge_tracked_job(
            _conn(), req.code, state=state_hint,
            match_score=req.match_score, match_json=req.match_json, tailor_json=req.tailor_json,
            company=req.company, title=req.title, url=req.url, salary=req.salary,
        )
        return {"status": "tracked", "state": final}

    @app.get("/api/tracked/{code}")
    def tracked_get(code: str) -> dict:
        tj = store.get_tracked_job(_conn(), code)
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

    @app.delete("/api/tracked/{code}")
    def untrack_job(code: str) -> dict:
        store.delete_tracked_job(_conn(), code)
        return {"status": "untracked"}

    @app.post("/api/tracked/{code}/offer")
    def tracked_set_offer(code: str, offer: OfferDetail) -> dict:
        if not code.strip():
            raise HTTPException(status_code=400, detail="缺少職缺代碼")
        final = store.set_tracked_state(_conn(), code, "offer", offer=offer)
        return {"status": "ok", "state": final}

    @app.post("/api/tracked/{code}/reject")
    def tracked_set_reject(code: str) -> dict:
        if not code.strip():
            raise HTTPException(status_code=400, detail="缺少職缺代碼")
        final = store.set_tracked_state(_conn(), code, "rejected")
        return {"status": "ok", "state": final}

    @app.post("/api/tracked/{code}/reset")
    def tracked_reset(code: str) -> dict:
        if not code.strip():
            raise HTTPException(status_code=400, detail="缺少職缺代碼")
        final = store.set_tracked_state(_conn(), code, "interested")
        return {"status": "ok", "state": final}

    @app.put("/api/tracked/{code}/interviews")
    def set_interviews_ep(code: str, req: _InterviewsReq) -> dict:
        if not code.strip():
            raise HTTPException(status_code=400, detail="缺少職缺代碼")
        store.set_interviews(_conn(), code, req.notes)
        return {"status": "ok", "count": len(req.notes)}

    app.include_router(settings.router)
    app.include_router(resume.router)
    app.include_router(dashboard.router)
    app.include_router(jobs.router)

    dist = Path(__file__).resolve().parents[3] / "web" / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")

    return app
