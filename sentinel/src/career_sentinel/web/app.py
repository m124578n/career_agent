from __future__ import annotations

import json
import logging
from pathlib import Path

from datetime import date, datetime

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import calendar_link, chat as chatmod, company_link, config, diagnosis, diff, digest, jobfetch, llm, match, pipeline, research, resume, store, tailor, usage as usagemod, watch
from ..models import ChatMessage, ChatState, ResumeState, Settings, SuggestedUpdate, TrackedJob, interview_key
from . import apply, runner, scheduler

logger = logging.getLogger("career_sentinel.web")


class _DiagnoseReq(BaseModel):
    target_title: str
    expected_salary: int | None = None


class _MatchReq(BaseModel):
    job_url: str


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


def _chat_events(messages, system):
    """依 provider 產聊天事件流：foundry 走工具迴圈、openai 走既有純聊天。"""
    if config.llm_provider() == "foundry":
        yield from chatmod.stream_with_tools(messages, system=system)
    else:
        for chunk in llm.chat_stream(messages, system=system, feature="整理助手"):
            yield {"type": "text", "text": chunk}


def _snapshot_payload(conn) -> dict:
    failed = runner.status()["last_failed_readers"]
    try:
        pipeline_jobs = [pj.model_dump() for pj in pipeline.build_pipeline(conn)]
    except Exception:
        pipeline_jobs = []
    try:
        tracked_codes = [tj.code for tj in store.load_tracked_jobs(conn)]
    except Exception:
        tracked_codes = []
    ids = store.latest_two_ids(conn)
    if not ids:
        return {
            "run_at": None,
            "viewers": [], "applications": [], "messages": [], "interviews": [],
            "pipeline": pipeline_jobs,
            "digest": "尚無資料，請先重新抓取",
            "failed_readers": failed,
            "tracked_codes": tracked_codes,
        }
    sid = ids[0]
    snap = store.load_snapshot(conn, sid)
    d = diff.diff_against_last(conn, sid)
    settings = store.load_settings(conn)
    dismissed = set(store.load_dismissed(conn).keys)
    return {
        "run_at": store.latest_run_at(conn),
        "viewers": [{"company": v.company, "job_title": v.job_title, "viewed_at": v.viewed_at, "watched": watch.is_watched(v.company, v.job_title, settings), "company_url": company_link.company_url_from_raw(v.raw)} for v in snap.viewers],
        "applications": [{"job_id": a.job_id, "company": a.company, "title": a.title, "status": a.status, "applied_at": a.applied_at, "watched": watch.is_watched(a.company, a.title, settings), "company_url": company_link.company_url_from_raw(a.raw), "job_url": company_link.job_url_from_raw(a.raw)} for a in snap.applications],
        "messages": [{"thread_id": m.thread_id, "company": m.company, "last_message": m.last_message, "has_interview_invite": m.has_interview_invite, "watched": watch.is_watched(m.company, m.last_message, settings), "company_url": company_link.company_url_from_raw(m.raw), "thread_url": company_link.chat_url_from_raw(m.raw)} for m in snap.messages],
        "interviews": [
            {
                "company": iv.company, "job_title": iv.job_title, "when": iv.when,
                "location": iv.location, "job_url": iv.job_url,
                "gcal_link": calendar_link.build_gcal_link(iv),
                "key": interview_key(iv),
                "dismissed": interview_key(iv) in dismissed,
                "company_url": company_link.company_url_from_raw(iv.raw),
                "thread_url": company_link.chat_url_from_raw(iv.raw),
            }
            for iv in sorted(snap.interviews, key=lambda iv: (iv.when == "", iv.when))
        ],
        "pipeline": pipeline_jobs,
        "digest": digest.render_human(d, snap),
        "failed_readers": failed,
        "tracked_codes": tracked_codes,
    }


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="career-sentinel")
    resolved_db = db_path or str(config.db_path())

    def _conn():
        return store.connect(resolved_db)

    scheduler.start(lambda: store.load_settings(_conn()))

    @app.get("/api/snapshot")
    def snapshot() -> dict:
        return _snapshot_payload(_conn())

    @app.post("/api/scrape")
    def scrape():
        if not runner.start_scrape(lambda: runner.default_scrape(resolved_db)):
            return JSONResponse({"status": "already_running"}, status_code=409)
        return {"status": "running"}

    @app.get("/api/status")
    def status() -> dict:
        return runner.status()

    @app.get("/api/usage")
    def usage_summary() -> dict:
        return usagemod.summary(_conn())

    @app.delete("/api/usage")
    def usage_reset() -> dict:
        usagemod.reset(_conn())
        return {"status": "reset"}

    @app.get("/api/schedule")
    def schedule() -> dict:
        return scheduler.state()

    @app.post("/api/schedule/ack")
    def schedule_ack() -> dict:
        scheduler.ack()
        return {"due": False}

    @app.get("/api/settings")
    def get_settings() -> dict:
        return store.load_settings(_conn()).model_dump()

    @app.put("/api/settings")
    def put_settings(settings: Settings) -> dict:
        store.save_settings(_conn(), settings)
        return settings.model_dump()

    @app.post("/api/resume/upload")
    async def resume_upload(file: UploadFile = File(...)) -> dict:
        data = await file.read()
        try:
            text = resume.parse_resume(file.filename or "resume", data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        conn = _conn()
        state = store.load_resume(conn)
        state.resume_text = text
        state.source = "upload"
        store.save_resume(conn, state)
        return {"chars": len(text)}

    @app.post("/api/resume/diagnose")
    def resume_diagnose(req: _DiagnoseReq) -> dict:
        conn = _conn()
        state = store.load_resume(conn)
        if not state.resume_text.strip():
            raise HTTPException(status_code=400, detail="請先上傳履歷")
        try:
            result = diagnosis.diagnose(state.resume_text, req.target_title, req.expected_salary)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=500, detail="健檢失敗，請重試")
        state.target_title = req.target_title
        state.expected_salary = req.expected_salary
        state.diagnosis = result
        store.save_resume(conn, state)
        return result.model_dump()

    @app.post("/api/resume/import104")
    def resume_import104() -> dict:
        from ..scraper import resume104 as r104
        if not runner.try_begin_browser():
            raise HTTPException(status_code=409, detail="瀏覽器忙碌中（可能正在抓取），請稍候再試")
        try:
            r = r104.resume104_session()
        except Exception:
            raise HTTPException(status_code=502, detail="讀取 104 履歷失敗，請重試")
        finally:
            runner.end_browser()
        if r is None:
            raise HTTPException(status_code=409, detail="尚未登入，請先在終端機執行：career-sentinel login")
        text = r104.flatten_for_diagnosis(r)
        if not text.strip():
            raise HTTPException(status_code=400, detail="104 履歷內容為空（可能未填寫），無法匯入")
        conn = _conn()
        state = store.load_resume(conn)
        state.resume_text = text
        state.source = "104"
        store.save_resume(conn, state)
        return {"chars": len(text), "resume104": r.model_dump()}

    @app.get("/api/resume")
    def resume_get() -> dict:
        state = store.load_resume(_conn())
        return {
            "has_resume": bool(state.resume_text.strip()),
            "chars": len(state.resume_text),
            "target_title": state.target_title,
            "expected_salary": state.expected_salary,
            "diagnosis": state.diagnosis.model_dump() if state.diagnosis else None,
            "source": state.source,
        }

    @app.post("/api/match")
    def match_job(req: _MatchReq) -> dict:
        conn = _conn()
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
            result = match.match(state.resume_text, state.target_title or "（未指定）", jd)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=500, detail="比對失敗，請重試")
        return {
            "title": jd.title, "company": jd.company, "salary": jd.salary,
            "score": result.score, "reasons": result.reasons, "gaps": result.gaps,
        }

    @app.post("/api/tailor")
    def tailor_job(req: _MatchReq) -> dict:
        conn = _conn()
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
            result = tailor.tailor_application(state.resume_text, state.target_title or "（未指定）", jd)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=500, detail="生成失敗，請重試")
        return result.model_dump()

    @app.post("/api/apply/open")
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

    @app.get("/api/search")
    def search(kw: str = "") -> dict:
        from ..scraper.search import fetch_search
        if not kw.strip():
            raise HTTPException(status_code=400, detail="請輸入搜尋關鍵字")
        try:
            jobs = fetch_search(kw.strip())
        except Exception:
            raise HTTPException(status_code=502, detail="搜尋失敗，請重試")
        settings = store.load_settings(_conn())
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

    @app.get("/api/recommend")
    def recommend() -> dict:
        from ..scraper.recommend import recommend_session
        if not runner.try_begin_browser():
            raise HTTPException(status_code=409, detail="瀏覽器忙碌中（可能正在抓取），請稍候再試")
        try:
            jobs = recommend_session()
        except Exception:
            raise HTTPException(status_code=502, detail="拉取推薦失敗，請重試")
        finally:
            runner.end_browser()
        if jobs is None:
            raise HTTPException(status_code=409, detail="尚未登入，請先在終端機執行：career-sentinel login")
        settings = store.load_settings(_conn())
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

    @app.post("/api/chat")
    def chat_send(req: _ChatReq):
        if not config.llm_provider():
            raise HTTPException(status_code=400, detail="請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")
        conn = _conn()
        system = chatmod.build_system_prompt(
            store.load_resume(conn), store.load_settings(conn),
            store.load_preferences(conn), store.load_memory(conn),
        )
        messages = chatmod.build_messages(store.load_chat(conn), req.message)
        settings_snapshot = store.load_settings(conn)

        def _sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        def gen():
            filt = chatmod.StreamFilter()
            clean_parts: list[str] = []
            try:
                for ev in _chat_events(messages, system):
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

    @app.get("/api/research")
    def research_get(company: str = "", force: int = 0) -> dict:
        name = company.strip()
        if not name:
            raise HTTPException(status_code=400, detail="請提供公司名稱")
        if not config.llm_provider():
            raise HTTPException(status_code=400, detail="請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")
        conn2 = _conn()
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
                    "match": None, "tailor": None}
        return {
            "code": tj.code, "found": True, "state": tj.state, "match_score": tj.match_score,
            "match": json.loads(tj.match_json) if tj.match_json else None,
            "tailor": json.loads(tj.tailor_json) if tj.tailor_json else None,
        }

    @app.delete("/api/tracked/{code}")
    def untrack_job(code: str) -> dict:
        store.delete_tracked_job(_conn(), code)
        return {"status": "untracked"}

    @app.get("/api/job")
    def job_by_url(url: str = "") -> dict:
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
        settings = store.load_settings(_conn())
        return {
            "code": code, "url": url, "title": jd.title, "company": jd.company,
            "salary": jd.salary, "is_watched": watch.is_watched(jd.company, jd.title, settings),
        }

    dist = Path(__file__).resolve().parents[3] / "web" / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")

    return app
