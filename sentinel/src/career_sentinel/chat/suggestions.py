"""求職總指揮：<suggestions> 建議區塊的解析、串流過濾與套用。"""
from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel

from .. import llm, store
from ..models import MemoryFact, SuggestedUpdate

SUGGESTIONS_OPEN = "<suggestions>"
SUGGESTIONS_CLOSE = "</suggestions>"


def _partial_marker_len(s: str) -> int:
    """s 尾端與 SUGGESTIONS_OPEN 開頭的最長重疊長度（處理標記跨 chunk）。"""
    for k in range(min(len(s), len(SUGGESTIONS_OPEN) - 1), 0, -1):
        if s.endswith(SUGGESTIONS_OPEN[:k]):
            return k
    return 0


class StreamFilter:
    """串流截斷狀態機：外流 <suggestions> 之前的文字，標記起全部截住供解析。"""

    def __init__(self) -> None:
        self._buf = ""
        self._capturing = False
        self._tail = ""

    def feed(self, chunk: str) -> str:
        if self._capturing:
            self._tail += chunk
            return ""
        self._buf += chunk
        idx = self._buf.find(SUGGESTIONS_OPEN)
        if idx != -1:
            out = self._buf[:idx]
            self._tail = self._buf[idx:]
            self._buf = ""
            self._capturing = True
            return out
        keep = _partial_marker_len(self._buf)
        out = self._buf[: len(self._buf) - keep]
        self._buf = self._buf[len(self._buf) - keep:]
        return out

    def finish(self) -> str:
        """串流結束：截留的尾端若不是標記，其實是一般文字，補吐出來。"""
        if self._capturing:
            return ""
        out = self._buf
        self._buf = ""
        return out

    def tail(self) -> str:
        return self._tail


def parse_suggestions(tail: str) -> list[SuggestedUpdate]:
    start = tail.find(SUGGESTIONS_OPEN)
    if start == -1:
        return []
    inner = tail[start + len(SUGGESTIONS_OPEN):]
    end = inner.find(SUGGESTIONS_CLOSE)
    if end != -1:
        inner = inner[:end]
    try:
        data = json.loads(llm._extract_json(inner))
        items = data.get("items")
        if not isinstance(items, list):
            return []
        return [SuggestedUpdate.model_validate(it) for it in items]
    except Exception:
        return []


ALLOWED: dict[str, set[str]] = {
    "target_title": {"set"},
    "expected_salary": {"set"},
    "locations": {"set"},
    "conditions": {"set"},
    "avoid": {"set"},
    "watched_companies": {"set"},
    "watched_keywords": {"set"},
    "resume_text": {"replace_snippet", "append_section"},
    "memory": {"remember", "forget"},
    "track": {"set"},
    "job_offer": {"set"},
    "job_reject": {"set"},
    "job_reset": {"set"},
    "untrack": {"set"},
    "interview_note": {"set"},
}


class ApplyResult(BaseModel):
    ok: bool
    message: str = ""


def _as_str_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if value is None or value == "":
        return []
    return [str(value)]


def apply_update(conn, upd: SuggestedUpdate) -> ApplyResult:
    ops = ALLOWED.get(upd.field)
    if ops is None or upd.op not in ops:
        return ApplyResult(ok=False, message=f"不允許的欄位或操作：{upd.field}/{upd.op}")
    if upd.field == "target_title":
        prefs = store.load_preferences(conn)
        prefs.target_title = str(upd.value or "")
        store.save_preferences(conn, prefs)
        return ApplyResult(ok=True)
    if upd.field == "expected_salary":
        prefs = store.load_preferences(conn)
        try:
            prefs.expected_salary = int(upd.value) if upd.value not in (None, "") else None
        except (TypeError, ValueError):
            return ApplyResult(ok=False, message="期望薪資需為數字")
        store.save_preferences(conn, prefs)
        return ApplyResult(ok=True)
    if upd.field in ("locations", "conditions", "avoid"):
        prefs = store.load_preferences(conn)
        setattr(prefs, upd.field, _as_str_list(upd.value))
        store.save_preferences(conn, prefs)
        return ApplyResult(ok=True)
    if upd.field in ("watched_companies", "watched_keywords"):
        settings = store.load_settings(conn)
        setattr(settings, upd.field, _as_str_list(upd.value))
        store.save_settings(conn, settings)
        return ApplyResult(ok=True)
    if upd.field == "resume_text":
        state = store.load_resume(conn)
        if upd.op == "append_section":
            state.resume_text = (state.resume_text.rstrip() + "\n\n" + str(upd.value or "")).strip()
        else:  # replace_snippet
            if not upd.old or upd.old not in state.resume_text:
                return ApplyResult(ok=False, message="找不到要替換的原文片段，請手動修改")
            state.resume_text = state.resume_text.replace(upd.old, upd.new or "", 1)
        store.save_resume(conn, state)
        return ApplyResult(ok=True)
    if upd.field in ("track", "job_offer", "job_reject", "job_reset", "untrack"):
        payload = upd.payload or {}
        code = str(payload.get("code", "")).strip()
        if not code:
            return ApplyResult(ok=False, message="缺少職缺代碼")
        if upd.field == "track":
            store.merge_tracked_job(
                conn, code, state="interested",
                company=str(payload.get("company", "")), title=str(payload.get("title", "")),
                url=str(payload.get("url", "")), salary=str(payload.get("salary", "")),
            )
            return ApplyResult(ok=True)
        if upd.field == "job_offer":
            from ..models import OfferDetail
            try:
                offer = OfferDetail(
                    salary_year=payload.get("salary_year"), salary_month=payload.get("salary_month"),
                    location=str(payload.get("location", "")), level=str(payload.get("level", "")),
                    start_date=str(payload.get("start_date", "")), notes=str(payload.get("notes", "")),
                )
            except Exception:
                return ApplyResult(ok=False, message="offer 明細格式錯誤（薪資需為數字）")
            store.set_tracked_state(conn, code, "offer", offer=offer)
            return ApplyResult(ok=True)
        if upd.field == "job_reject":
            store.set_tracked_state(conn, code, "rejected")
            return ApplyResult(ok=True)
        if upd.field == "job_reset":
            store.set_tracked_state(conn, code, "interested")
            return ApplyResult(ok=True)
        store.delete_tracked_job(conn, code)  # untrack
        return ApplyResult(ok=True)
    if upd.field == "interview_note":
        payload = upd.payload or {}
        code = str(payload.get("code", "")).strip()
        if not code:
            return ApplyResult(ok=False, message="缺少職缺代碼")
        from ..models import InterviewNote
        store.add_interview_note(conn, code, InterviewNote(
            when=str(payload.get("when", "")), content=str(payload.get("content", ""))))
        return ApplyResult(ok=True)
    if upd.field == "memory":
        # memory / remember / forget（LLM 自動維護：重複不再記、過時的可刪）
        mem = store.load_memory(conn)
        text = str(upd.value or "").strip()
        if not text:
            return ApplyResult(ok=False, message="記憶內容為空")
        if upd.op == "forget":
            kept = [f for f in mem.facts if f.text.strip() != text]
            if len(kept) == len(mem.facts):
                return ApplyResult(ok=False, message="找不到要刪除的記憶")
            mem.facts = kept
            store.save_memory(conn, mem)
            return ApplyResult(ok=True)
        if any(f.text.strip() == text for f in mem.facts):
            return ApplyResult(ok=False, message="已有相同記憶，略過")
        mem.facts.append(MemoryFact(
            text=text,
            created_at=datetime.now().isoformat(timespec="seconds"),
        ))
        store.save_memory(conn, mem)
        return ApplyResult(ok=True)
    return ApplyResult(ok=False, message=f"不允許的欄位或操作：{upd.field}/{upd.op}")
