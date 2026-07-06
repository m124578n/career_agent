"""SP8 整理助手服務層：prompt 組裝、串流截斷、建議解析、套用、compact。"""
from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel

from . import llm, store, usage
from .models import (
    ChatState, JobPreferences, MemoryFact, MemoryState, ResumeState, Settings, SuggestedUpdate,
)

SUGGESTIONS_OPEN = "<suggestions>"
SUGGESTIONS_CLOSE = "</suggestions>"
COMPACT_THRESHOLD = 30  # messages 超過此數觸發 compact
COMPACT_KEEP = 10       # compact 後保留的近期逐字訊息數
CURATE_THRESHOLD = 12   # memory facts 超過此數觸發 LLM 整理
TOOL_LOOP_MAX = 2       # 每輪對話最多執行幾次工具
JOBS_RESULT_LIMIT = 8   # tool_result 給 LLM 的精簡職缺數上限
_RESUME_MAX_CHARS = 8000

_CONTRACT = """
當對話中出現應更新上述狀態的資訊時，在回覆文字結束後（最後）輸出一個建議區塊，格式：
<suggestions>{"items": [
  {"field": "expected_salary", "op": "set", "value": 60000},
  {"field": "locations", "op": "set", "value": ["台北", "新北"]},
  {"field": "resume_text", "op": "replace_snippet", "old": "原文片段", "new": "改後片段"},
  {"field": "resume_text", "op": "append_section", "value": "要附加的新段落"},
  {"field": "memory", "op": "remember", "value": "值得長期記住的使用者事實"},
  {"field": "memory", "op": "forget", "value": "要刪除的既有記憶原文"}
]}</suggestions>
規則：
- 允許的 field/op：target_title/set、expected_salary/set（value 為整數**月薪**；
  使用者若說年薪，先除以 12 四捨五入換算成月薪再填，並在回覆中說明換算結果）、
  locations/set、conditions/set、avoid/set、watched_companies/set、watched_keywords/set
  （list 類 value 為完整字串列表，整列表取代）、
  resume_text/replace_snippet（old 必須逐字取自履歷全文）、resume_text/append_section、
  memory/remember（只記長期有效的偏好與事實，不記一次性資訊；「長期記憶」清單已有的
  內容——包括同義改寫——不要重複 remember）、
  memory/forget（既有記憶過時或與新資訊矛盾時，主動輸出 forget 刪除舊記憶——value 需
  逐字等於清單中該條原文——並視需要接著 remember 更新後的內容，保持記憶清單精簡不重複）。
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
        f"- 目標職稱：{prefs.target_title or '（未設定）'}\n"
        f"- 期望月薪：{prefs.expected_salary or '（未設定）'}\n"
        f"- 求職偏好：地點={prefs.locations}；軟條件={prefs.conditions}；避雷={prefs.avoid}\n"
        f"- 關注公司：{settings.watched_companies}；關注關鍵字：{settings.watched_keywords}\n\n"
        f"長期記憶（半永久）：\n{mem_lines}\n\n"
        "工具：你有 search_jobs 工具可搜尋 104 職缺。"
        "只在使用者明確要求找職缺時使用 search_jobs；關鍵字精簡（2–4 個詞）；每輪對話至多 2 次。\n\n"
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


def build_export_md(
    resume: ResumeState, settings: Settings, prefs: JobPreferences,
    memory: MemoryState, state: ChatState,
) -> str:
    """匯出求職檔案 Markdown：帶到其他 LLM 平台繼續討論規劃用。"""
    mem_lines = "\n".join(f"- {f.text}" for f in memory.facts) or "（無）"
    lines = [
        "# 我的求職檔案（career-sentinel 匯出）",
        f"> 匯出時間：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "以下是我的求職背景資料，請以此為基礎與我討論求職規劃。",
        "",
        "## 基本目標",
        f"- 目標職稱：{prefs.target_title or '（未設定）'}",
        f"- 期望月薪：{prefs.expected_salary or '（未設定）'}",
        "",
        "## 求職偏好",
        f"- 地點：{'、'.join(prefs.locations) or '（未設定）'}",
        f"- 軟條件：{'、'.join(prefs.conditions) or '（未設定）'}",
        f"- 避雷：{'、'.join(prefs.avoid) or '（未設定）'}",
        "",
        "## 關注清單",
        f"- 公司：{'、'.join(settings.watched_companies) or '（無）'}",
        f"- 關鍵字：{'、'.join(settings.watched_keywords) or '（無）'}",
        "",
        "## 長期記憶（助手整理的個人偏好與事實）",
        mem_lines,
    ]
    if state.summary:
        lines += ["", "## 先前討論摘要", state.summary]
    lines += ["", "## 履歷全文", resume.resume_text or "（尚未上傳履歷）", ""]
    return "\n".join(lines)


TOOLS = [{
    "name": "search_jobs",
    "description": "在 104 站內以關鍵字搜尋職缺。只在使用者明確要求找職缺時使用。",
    "input_schema": {
        "type": "object",
        "properties": {"keyword": {"type": "string", "description": "精簡的搜尋關鍵字"}},
        "required": ["keyword"],
    },
}]


def _execute_search(keyword: str):
    """執行站內搜尋工具。回 (jobs, tool_result文字, is_error)。"""
    from .scraper import search as search_mod

    if not keyword.strip():
        return [], "搜尋失敗：關鍵字為空", True
    try:
        jobs = search_mod.fetch_search(keyword.strip())
    except Exception as exc:
        return [], f"搜尋失敗：{exc}", True
    brief = [
        {"title": j.title, "company": j.company, "salary": j.salary, "url": j.url}
        for j in jobs[:JOBS_RESULT_LIMIT]
    ]
    return jobs, json.dumps(brief, ensure_ascii=False), False


def stream_with_tools(messages: list[dict], *, system: str, client=None, feature: str = "整理助手"):
    """Foundry 原生 tool use 串流：yield {"type":"text"} 與 {"type":"jobs"} 事件。

    工具執行達 TOOL_LOOP_MAX 後，最後一輪不帶 tools 強制作答。
    """
    from .config import foundry_settings

    fs = foundry_settings()
    if client is None:
        from anthropic import AnthropicFoundry

        client = AnthropicFoundry(api_key=fs.api_key, base_url=fs.base_url, timeout=180)
    system = llm._with_today(system)
    msgs = list(messages)
    tool_runs = 0
    # 結構性終止上限：即使 provider 在無 tools 輪仍回 tool_use 也不會無限迴圈
    for _ in range(TOOL_LOOP_MAX + 1):
        kwargs: dict = {
            "model": fs.model, "max_tokens": 4096,
            "system": system, "messages": msgs,
        }
        if tool_runs < TOOL_LOOP_MAX:
            kwargs["tools"] = TOOLS
        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield {"type": "text", "text": text}
            final = stream.get_final_message()
        usage.record(feature, fs.model, getattr(final, "usage", None))
        if final.stop_reason != "tool_use":
            return
        results = []
        for block in final.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            keyword = str((block.input or {}).get("keyword", ""))
            jobs, result_text, is_error = _execute_search(keyword)
            tool_runs += 1
            if not is_error:
                yield {"type": "jobs", "keyword": keyword, "items": jobs}
            entry = {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
            if is_error:
                entry["is_error"] = True
            results.append(entry)
        msgs = msgs + [
            {"role": "assistant", "content": final.content},
            {"role": "user", "content": results},
        ]
