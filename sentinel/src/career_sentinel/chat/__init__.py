"""SP8 整理助手服務層：prompt 組裝、串流截斷、建議解析、套用、compact。"""
from __future__ import annotations

import html as _html
import json
import re as _re
from datetime import datetime

from pydantic import BaseModel

from .. import llm, pipeline, store, usage
from ..models import (
    ChatState, JobPreferences, MemoryFact, MemoryState, PipelineJob, ResumeState, Settings, SuggestedUpdate,
)

SUGGESTIONS_OPEN = "<suggestions>"
SUGGESTIONS_CLOSE = "</suggestions>"
COMPACT_THRESHOLD = 30  # messages 超過此數觸發 compact
COMPACT_KEEP = 10       # compact 後保留的近期逐字訊息數
CURATE_THRESHOLD = 12   # memory facts 超過此數觸發 LLM 整理
TOOL_LOOP_MAX = 4       # 每輪對話最多執行幾次工具
JOBS_RESULT_LIMIT = 8   # tool_result 給 LLM 的精簡職缺數上限
_RESUME_MAX_CHARS = 8000
_PIPE_GROUP_LIMIT = 5  # 每組摘要最多列幾筆
_PIPE_STATE_ORDER = ["interviewing", "offer", "applied", "tailored", "matched", "interested", "rejected"]
_PIPE_STATE_LABEL = {
    "interviewing": "面試中", "offer": "offer", "applied": "已投遞",
    "tailored": "已客製化", "matched": "已比對", "interested": "有興趣", "rejected": "未錄取",
}


def format_pipeline_summary(jobs: list[PipelineJob]) -> str:
    """把 build_pipeline 結果壓成給 system prompt 的精簡摘要（含 code 供引用）。空則回 ''。"""
    if not jobs:
        return ""
    groups: dict[str, list[PipelineJob]] = {}
    for j in jobs:
        groups.setdefault(j.state, []).append(j)
    lines: list[str] = []
    for state in _PIPE_STATE_ORDER:
        items = groups.get(state) or []
        if not items:
            continue
        lines.append(f"- {_PIPE_STATE_LABEL.get(state, state)}（{len(items)} 筆）：")
        for j in items[:_PIPE_GROUP_LIMIT]:
            extra = ""
            if state == "interviewing" and j.when:
                extra = f"，面試 {j.when}"
            elif state == "offer" and j.offer:
                if j.offer.salary_year is not None:
                    extra = f"，年薪 {j.offer.salary_year}"
                elif j.offer.salary_month is not None:
                    extra = f"，月薪 {j.offer.salary_month}"
            code = f"（{j.code}）" if j.code else ""
            lines.append(f"  · {j.company} · {j.title}{code}{extra}")
    return "\n".join(lines)

_CONTRACT = """
當對話中出現應更新上述狀態的資訊，或使用者要對職缺採取管道動作時，在回覆文字結束後（最後）輸出一個建議區塊，格式：
<suggestions>{"items": [
  {"field": "expected_salary", "op": "set", "value": 60000},
  {"field": "locations", "op": "set", "value": ["台北", "新北"]},
  {"field": "resume_text", "op": "replace_snippet", "old": "原文片段", "new": "改後片段"},
  {"field": "resume_text", "op": "append_section", "value": "要附加的新段落"},
  {"field": "memory", "op": "remember", "value": "值得長期記住的使用者事實"},
  {"field": "memory", "op": "forget", "value": "要刪除的既有記憶原文"},
  {"field": "track", "op": "set", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師", "url": "https://www.104.com.tw/job/abc12", "salary": "月薪6萬"}},
  {"field": "job_offer", "op": "set", "payload": {"code": "abc12", "salary_year": 1200000, "location": "台北", "level": "資深", "start_date": "2026-09-01", "notes": "含年終"}},
  {"field": "job_reject", "op": "set", "payload": {"code": "abc12", "company": "台積電"}},
  {"field": "job_reset", "op": "set", "payload": {"code": "abc12", "company": "台積電"}},
  {"field": "untrack", "op": "set", "payload": {"code": "abc12", "company": "台積電"}},
  {"field": "tailor", "op": "run", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師"}},
  {"field": "negotiate", "op": "run", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師"}},
  {"field": "interview_note", "op": "set", "payload": {"code": "abc12", "when": "2026-07-10 14:00 一面", "content": "問了系統設計與過往專案"}}
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
- 管道動作（track/job_offer/job_reject/job_reset/untrack）：一律用 payload 帶資料。
  track＝把職缺加入管道（追蹤）；job_offer＝標記錄取並記 offer 明細（payload 的 salary_year/
  salary_month 為整數，使用者說年薪填 salary_year、月薪填 salary_month）；job_reject＝標記未錄取；
  job_reset＝重設狀態；untrack＝取消追蹤。payload.code 必須來自 get_pipeline 或 search_jobs 的
  實際結果，**不得杜撰**。這些動作只是「提議」，會等使用者按下確認才生效——**不要在回覆中聲稱已完成**。
- 客製化（tailor/run）：使用者想要某職缺的客製化履歷與求職信時，提議
  {"field": "tailor", "op": "run", "payload": {"code": "...", "company": "...", "title": "..."}}.
  需使用者已上傳履歷；payload.code 必來自 get_pipeline/search_jobs/get_job_detail 的實際結果、不得杜撰。
  這是**提議**，會等使用者按下「客製化」才實際生成（花 LLM 錢）——**你不要自行寫出客製化內容或聲稱已完成**，只丟提議卡。
- 談判建議（negotiate/run）：使用者想要某 **offer** 的議價策略與話術時，提議
  {"field": "negotiate", "op": "run", "payload": {"code": "...", "company": "...", "title": "..."}}.
  僅對已標記錄取（offer）的職缺；payload.code 必來自 get_pipeline 的實際 offer 職缺、不得杜撰。
  這是**提議**，等使用者按下才實際生成（花 LLM 錢＋web search）——**你不要自行寫議價策略或聲稱已完成**，只丟提議卡。
- 面試紀錄（interview_note/set）：使用者描述某職缺的面試（時間、問了什麼、心得）時，提議
  {"field": "interview_note", "op": "set", "payload": {"code": "...", "when": "...", "content": "..."}}.
  payload.code 必來自 get_pipeline/search_jobs 的實際結果、不得杜撰；只提議，按下確認才記。
- 沒有要更新時不要輸出 <suggestions> 區塊。
- <suggestions> 之後不要再有任何文字。
"""


def build_system_prompt(
    resume: ResumeState, settings: Settings, prefs: JobPreferences, memory: MemoryState,
    pipeline_summary: str = "",
) -> str:
    mem_lines = "\n".join(f"- {f.text}" for f in memory.facts) or "（無）"
    resume_text = resume.resume_text[:_RESUME_MAX_CHARS] or "（尚未上傳履歷）"
    head = (
        "你是「career-sentinel 求職總指揮」：用繁體中文陪使用者跑完整條求職流程"
        "（整理履歷與偏好、找職缺、追蹤管道、記錄 offer）。回覆口語、精簡。\n\n"
        "目前狀態：\n"
        f"- 今天日期：{datetime.now().strftime('%Y-%m-%d')}\n"
        f"- 目標職稱：{prefs.target_title or '（未設定）'}\n"
        f"- 期望月薪：{prefs.expected_salary or '（未設定）'}\n"
        f"- 求職偏好：地點={prefs.locations}；軟條件={prefs.conditions}；避雷={prefs.avoid}\n"
        f"- 關注公司：{settings.watched_companies}；關注關鍵字：{settings.watched_keywords}\n\n"
        f"長期記憶（半永久）：\n{mem_lines}\n\n"
        f"目前求職管道：\n{pipeline_summary or '（管道目前無職缺）'}\n\n"
        "工具：search_jobs 用關鍵字搜尋 104 職缺（使用者明確要找才用，關鍵字精簡 2–4 個詞；"
        "每頁 20 筆，使用者要『下一頁/再多找一些』時用同一關鍵字、page 遞增再搜）；"
        "get_pipeline 讀你目前的求職管道（要引用或操作既有職缺前，先用它確認 code 與現況）；"
        "get_job_detail 讀指定職缺的完整 JD（傳 code 或網址；回答職缺細節、比較、給建議前先讀）；"
        "fetch_url 讀任意網址內容（使用者貼網址要你看/分析職缺時用；非 104 站也可）。工具呼叫請節制。\n\n"
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


TOOLS = [
    {
        "name": "search_jobs",
        "description": (
            "在 104 站內以關鍵字搜尋職缺，每頁 20 筆。只在使用者明確要求找職缺時使用。"
            "使用者要『下一頁 / 再多找一些 / 繼續往下』時，用同一個 keyword、page 遞增再呼叫一次。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "精簡的搜尋關鍵字"},
                "page": {
                    "type": "integer",
                    "description": "1 起算的頁碼，預設 1；往下翻更多職缺時用同一關鍵字遞增。",
                    "minimum": 1,
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_pipeline",
        "description": "讀取使用者目前的求職管道（各狀態職缺、offer 明細、面試時間、job code）。要引用或操作既有職缺前先用它確認 code 與現況。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_job_detail",
        "description": "抓取指定 104 職缺的完整 JD（職務內容、需求條件、薪資、地點）。可傳 job code 或 104 職缺網址。回答職缺問題、比較職缺、給客製化建議前用它讀 JD。",
        "input_schema": {
            "type": "object",
            "properties": {"code_or_url": {"type": "string", "description": "104 job code 或職缺網址"}},
            "required": ["code_or_url"],
        },
    },
    {
        "name": "fetch_url",
        "description": "讀取任意網址的內容（職缺頁、文章等）。使用者貼上網址要你看或分析時用。104 職缺會回結構化 JD；其他網站回去標籤後的純文字。若是需要 JavaScript 才顯示的頁面可能抓不到，會請使用者改貼文字。",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "要讀取的網址（http/https）"}},
            "required": ["url"],
        },
    },
]


def _execute_search(keyword: str, page: int = 1):
    """執行站內搜尋工具。回 (jobs, tool_result文字, is_error)。page 為 1 起算頁碼。"""
    from ..scraper import search as search_mod

    if not keyword.strip():
        return [], "搜尋失敗：關鍵字為空", True
    page = max(1, page)
    try:
        jobs = search_mod.fetch_search(keyword.strip(), page=page)
    except Exception as exc:
        return [], f"搜尋失敗：{exc}", True
    brief = [
        {"title": j.title, "company": j.company, "salary": j.salary, "url": j.url}
        for j in jobs[:JOBS_RESULT_LIMIT]
    ]
    # 告知目前頁與是否還有下一頁，讓 LLM 知道可用 page+1 續搜
    has_more = len(jobs) >= 20
    payload = {
        "page": page,
        "count": len(jobs),
        "has_more": has_more,
        "next_page": page + 1 if has_more else None,
        "jobs": brief,
    }
    return jobs, json.dumps(payload, ensure_ascii=False), False


_FETCH_URL_MAX = 3000  # 通用抓取文字截斷（控 token）
_SCRIPT_STYLE_RE = _re.compile(r"<(script|style)[^>]*>.*?</\1>", _re.DOTALL | _re.IGNORECASE)
_TAG_RE = _re.compile(r"<[^>]+>")
_WS_RE = _re.compile(r"[ \t\r\f\v]+")
_MULTINL_RE = _re.compile(r"\n{3,}")


def _html_to_text(html_text: str) -> str:
    """粗略把 HTML 轉純文字：去 script/style、去標籤、還原 entity、收斂空白。"""
    t = _SCRIPT_STYLE_RE.sub(" ", html_text or "")
    t = _TAG_RE.sub(" ", t)
    t = _html.unescape(t)
    t = _WS_RE.sub(" ", t)
    t = _MULTINL_RE.sub("\n\n", t)
    return t.strip()


def _execute_fetch_url(url: str):
    """fetch_url 執行體。回 (None, result_text, is_error)。唯讀、需真網路。
    104 職缺網址走結構化 JD；其他網址通用抓取去標籤。"""
    raw = (url or "").strip()
    if not raw:
        return None, "缺少網址", True
    if not raw.startswith(("http://", "https://")):
        return None, "請提供有效網址（http/https 開頭）", True
    from .. import jobfetch
    try:
        jobfetch.extract_job_code(raw)   # 是 104 職缺網址就走結構化 JD
        return _execute_job_detail(raw)
    except ValueError:
        pass
    try:
        from curl_cffi import requests as creq
        resp = creq.get(raw, impersonate="chrome", timeout=30)
        resp.raise_for_status()
        html_text = resp.text
    except Exception:
        return None, "抓取網頁失敗，請確認網址或直接貼上內容文字", True
    text = _html_to_text(html_text)
    if len(text) < 50:
        return None, "這頁可能需要 JavaScript 才顯示內容，抓不到；請直接貼上職缺內容文字", True
    return None, json.dumps({"url": raw, "text": text[:_FETCH_URL_MAX]}, ensure_ascii=False), False


_JD_DESC_MAX = 1500  # JD description 截斷（控 token）


def _execute_job_detail(code_or_url: str):
    """get_job_detail 執行體。回 (None, result_text, is_error)。唯讀、需真網路。"""
    from .. import jobfetch

    raw = (code_or_url or "").strip()
    if not raw:
        return None, "缺少職缺代碼或網址", True
    if "/job/" in raw or "104.com.tw" in raw:
        try:
            code = jobfetch.extract_job_code(raw)
        except ValueError:
            return None, "無法從網址取得 104 職缺代碼（請確認是 104 職缺網址）", True
    else:
        code = raw
    try:
        jd = jobfetch.fetch_job_detail(code)
    except Exception:
        return None, "抓取職缺詳情失敗，請確認代碼或稍後再試", True
    brief = {
        "code": code, "title": jd.title, "company": jd.company, "salary": jd.salary,
        "location": jd.location, "work_exp": jd.work_exp, "education": jd.education,
        "majors": jd.majors, "specialties": jd.specialties,
        "description": (jd.description or "")[:_JD_DESC_MAX],
    }
    return None, json.dumps(brief, ensure_ascii=False), False


def _pipeline_tool_json(db_path: str | None) -> str:
    """get_pipeline 執行體：開新連線讀管道，回精簡 JSON（唯讀 best-effort）。"""
    if not db_path:
        return "[]"
    try:
        conn = store.connect(db_path)
        jobs = pipeline.build_pipeline(conn)
    except Exception:
        return "[]"
    brief = [
        {"code": j.code, "company": j.company, "title": j.title, "state": j.state,
         "salary": j.salary, "match_score": j.match_score, "when": j.when,
         "offer": j.offer.model_dump() if j.offer else None}
        for j in jobs
    ]
    return json.dumps(brief, ensure_ascii=False)


def _execute_tool(name: str, tool_input: dict, db_path: str | None):
    """工具分派。回 (event_dict_or_None, result_text, is_error)。event 供 yield 給前端（如 jobs）。"""
    if name == "search_jobs":
        keyword = str((tool_input or {}).get("keyword", ""))
        try:
            page = int((tool_input or {}).get("page", 1) or 1)
        except (TypeError, ValueError):
            page = 1
        jobs, result_text, is_error = _execute_search(keyword, page)
        event = None if is_error else {"type": "jobs", "keyword": keyword, "page": max(1, page), "items": jobs}
        return event, result_text, is_error
    if name == "get_pipeline":
        return None, _pipeline_tool_json(db_path), False
    if name == "get_job_detail":
        return _execute_job_detail(str((tool_input or {}).get("code_or_url", "")))
    if name == "fetch_url":
        return _execute_fetch_url(str((tool_input or {}).get("url", "")))
    return None, f"未知工具：{name}", True


def stream_with_tools(messages: list[dict], *, system: str, client=None, feature: str = "整理助手", db_path: str | None = None):
    """Foundry 原生 tool use 串流：yield {"type":"text"} 與 {"type":"jobs"} 事件。

    工具執行達 TOOL_LOOP_MAX 後，最後一輪不帶 tools 強制作答。
    """
    from ..config import foundry_settings

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
            event, result_text, is_error = _execute_tool(
                getattr(block, "name", ""), block.input or {}, db_path)
            tool_runs += 1
            if event is not None:
                yield event
            entry = {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
            if is_error:
                entry["is_error"] = True
            results.append(entry)
        msgs = msgs + [
            {"role": "assistant", "content": final.content},
            {"role": "user", "content": results},
        ]
