"""求職總指揮：對話壓縮（compact）與長期記憶整理（curate）。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .. import llm, store
from ..models import ChatState, MemoryFact

COMPACT_THRESHOLD = 30  # messages 超過此數觸發 compact
COMPACT_KEEP = 10       # compact 後保留的近期逐字訊息數
CURATE_THRESHOLD = 12   # memory facts 超過此數觸發 LLM 整理


def maybe_compact(conn, state: ChatState) -> ChatState:
    """messages 超過門檻時把舊訊息壓成 summary、留最近 COMPACT_KEEP 則。失敗整個跳過。"""
    if len(state.messages) <= COMPACT_THRESHOLD:
        return state
    old = state.messages[:-COMPACT_KEEP]
    recent = state.messages[-COMPACT_KEEP:]
    lines = "\n".join(f"{m.role}: {m.content}" for m in old)
    prompt = (
        ("先前摘要：\n" + state.summary + "\n\n" if state.summary else "")
        + "以下是求職整理對話的較舊片段，請壓縮成一段保留關鍵事實與決定的摘要（500 字內），"
        + "直接輸出摘要文字：\n" + lines
    )
    try:
        new_summary = "".join(llm.chat_stream(
            [{"role": "user", "content": prompt}], feature="整理助手"))
    except Exception:
        return state  # 失敗跳過、下輪再試，永不丟逐字訊息
    if not new_summary.strip():
        return state
    new_state = ChatState(summary=new_summary.strip(), messages=recent)
    store.save_chat(conn, new_state)  # 先寫入新 summary+裁切後訊息（單一原子寫）
    return new_state


class CuratedFacts(BaseModel):
    facts: list[str] = []


def maybe_curate_memory(conn) -> None:
    """memory 超過門檻時用 LLM 整理（合併同義、依時間去過時矛盾）。失敗跳過、絕不清空。"""
    mem = store.load_memory(conn)
    if len(mem.facts) <= CURATE_THRESHOLD:
        return
    lines = "\n".join(f"- {f.text}（記於 {f.created_at}）" for f in mem.facts)
    prompt = (
        "以下是求職助手為使用者累積的長期記憶清單。請整理：合併重複與同義項、"
        "刪除已被較新資訊取代或互相矛盾的舊項（以記錄時間較新者為準）、"
        "保留所有仍有效的獨立事實，每條一句話。"
        '只輸出 JSON：{"facts": ["..."]}\n\n' + lines
    )
    try:
        curated = llm.parse_json(prompt, CuratedFacts, feature="整理助手")
    except Exception:
        return  # 失敗跳過，下輪再試
    texts = [t.strip() for t in curated.facts if t.strip()]
    if not texts or len(texts) > len(mem.facts):
        return  # 空清單或越整理越多都不採用
    by_text = {f.text: f for f in mem.facts}
    now = datetime.now().isoformat(timespec="seconds")
    mem.facts = [by_text.get(t) or MemoryFact(text=t, created_at=now) for t in texts]
    store.save_memory(conn, mem)
