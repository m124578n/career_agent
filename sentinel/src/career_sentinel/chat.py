"""SP8 整理助手服務層：prompt 組裝、串流截斷、建議解析、套用、compact。"""
from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel

from . import llm, store
from .models import (
    ChatState, JobPreferences, MemoryFact, MemoryState, ResumeState, Settings, SuggestedUpdate,
)

SUGGESTIONS_OPEN = "<suggestions>"
SUGGESTIONS_CLOSE = "</suggestions>"
COMPACT_THRESHOLD = 30  # messages 超過此數觸發 compact
COMPACT_KEEP = 10       # compact 後保留的近期逐字訊息數
_RESUME_MAX_CHARS = 8000

_CONTRACT = """
當對話中出現應更新上述狀態的資訊時，在回覆文字結束後（最後）輸出一個建議區塊，格式：
<suggestions>{"items": [
  {"field": "expected_salary", "op": "set", "value": 900000},
  {"field": "locations", "op": "set", "value": ["台北", "新北"]},
  {"field": "resume_text", "op": "replace_snippet", "old": "原文片段", "new": "改後片段"},
  {"field": "resume_text", "op": "append_section", "value": "要附加的新段落"},
  {"field": "memory", "op": "remember", "value": "值得長期記住的使用者事實"}
]}</suggestions>
規則：
- 允許的 field/op：target_title/set、expected_salary/set（value 為整數年薪）、
  locations/set、conditions/set、avoid/set、watched_companies/set、watched_keywords/set
  （list 類 value 為完整字串列表，整列表取代）、
  resume_text/replace_snippet（old 必須逐字取自履歷全文）、resume_text/append_section、
  memory/remember（只記長期有效的偏好與事實，不記一次性資訊）。
- 沒有要更新時不要輸出 <suggestions> 區塊。
- <suggestions> 之後不要再有任何文字。
"""


def build_system_prompt(
    resume: ResumeState, settings: Settings, prefs: JobPreferences, memory: MemoryState,
) -> str:
    mem_lines = "\n".join(f"- {f.text}" for f in memory.facts) or "（無）"
    resume_text = resume.resume_text[:_RESUME_MAX_CHARS] or "（尚未上傳履歷）"
    head = (
        "你是「career-sentinel 整理助手」：用繁體中文陪使用者整理履歷與求職偏好。回覆口語、精簡。\n\n"
        "目前狀態：\n"
        f"- 目標職稱：{resume.target_title or '（未設定）'}\n"
        f"- 期望薪資：{resume.expected_salary or '（未設定）'}\n"
        f"- 求職偏好：地點={prefs.locations}；軟條件={prefs.conditions}；避雷={prefs.avoid}\n"
        f"- 關注公司：{settings.watched_companies}；關注關鍵字：{settings.watched_keywords}\n\n"
        f"長期記憶（半永久）：\n{mem_lines}\n\n"
        f"履歷全文（前 {_RESUME_MAX_CHARS} 字）：\n{resume_text}\n"
    )
    return head + _CONTRACT


def build_messages(state: ChatState, user_msg: str) -> list[dict]:
    msgs: list[dict] = []
    if state.summary:
        msgs.append({"role": "user", "content": "（先前對話摘要）" + state.summary})
        msgs.append({"role": "assistant", "content": "好的，我已掌握先前的討論脈絡。"})
    msgs.extend({"role": m.role, "content": m.content} for m in state.messages)
    msgs.append({"role": "user", "content": user_msg})
    return msgs


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
