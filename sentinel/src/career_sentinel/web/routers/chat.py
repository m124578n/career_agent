"""chat 路由：串流聊天 / 套用建議 / 讀取 / 清空 / 匯出 / 刪記憶。"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ... import chat as chatmod, config, llm, pipeline, store, watch
from ...models import ChatMessage, ChatState, SuggestedUpdate
from ..deps import get_db_path

router = APIRouter()


class _ChatReq(BaseModel):
    message: str


def _chat_events(messages, system, db_path=None):
    """依 provider 產聊天事件流：foundry 走工具迴圈、openai 走既有純聊天。"""
    if config.llm_provider() == "foundry":
        yield from chatmod.stream_with_tools(messages, system=system, db_path=db_path)
    else:
        for chunk in llm.chat_stream(messages, system=system, feature="整理助手"):
            yield {"type": "text", "text": chunk}


@router.post("/api/chat")
def chat_send(req: _ChatReq, db_path: str = Depends(get_db_path)):
    if not config.llm_provider():
        raise HTTPException(status_code=400, detail="請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")
    conn = store.connect(db_path)
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
            for ev in _chat_events(messages, system, db_path):
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
        gconn = store.connect(db_path)  # generator 可能跑在不同執行緒，sqlite 連線在此建立
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


@router.post("/api/chat/apply")
def chat_apply(upd: SuggestedUpdate, db_path: str = Depends(get_db_path)) -> dict:
    res = chatmod.apply_update(store.connect(db_path), upd)
    if not res.ok and res.message.startswith("不允許"):
        raise HTTPException(status_code=400, detail=res.message)
    return res.model_dump()


@router.get("/api/chat")
def chat_get(db_path: str = Depends(get_db_path)) -> dict:
    conn2 = store.connect(db_path)
    st = store.load_chat(conn2)
    mem = store.load_memory(conn2)
    return {
        "summary": st.summary,
        "messages": [m.model_dump() for m in st.messages],
        "memory": [f.model_dump() for f in mem.facts],
    }


@router.delete("/api/chat")
def chat_clear(db_path: str = Depends(get_db_path)) -> dict:
    store.save_chat(store.connect(db_path), ChatState())
    return {"ok": True}


@router.get("/api/export")
def export_md(db_path: str = Depends(get_db_path)) -> Response:
    conn2 = store.connect(db_path)
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


@router.delete("/api/memory/{index}")
def memory_delete(index: int, db_path: str = Depends(get_db_path)) -> dict:
    conn2 = store.connect(db_path)
    mem = store.load_memory(conn2)
    if not (0 <= index < len(mem.facts)):
        raise HTTPException(status_code=404, detail="memory 不存在")
    mem.facts.pop(index)
    store.save_memory(conn2, mem)
    return {"ok": True}
