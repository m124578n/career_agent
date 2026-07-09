"""SP8 整理助手服務層：prompt 組裝、串流截斷、建議解析、套用、compact。"""
from __future__ import annotations

import html as _html
import json
import re as _re
from datetime import datetime

from .. import llm, pipeline, store, usage
from ..models import (
    ChatState, JobPreferences, MemoryFact, MemoryState, PipelineJob, ResumeState, Settings, SuggestedUpdate,
)
from .memory import (  # noqa: F401
    COMPACT_KEEP, COMPACT_THRESHOLD, CURATE_THRESHOLD, CuratedFacts,
    maybe_compact, maybe_curate_memory,
)
from .export import build_export_md  # noqa: F401
from .prompt import build_messages, build_system_prompt, format_pipeline_summary  # noqa: F401
from .suggestions import ApplyResult, StreamFilter, apply_update, parse_suggestions  # noqa: F401

TOOL_LOOP_MAX = 4       # 每輪對話最多執行幾次工具
JOBS_RESULT_LIMIT = 8   # tool_result 給 LLM 的精簡職缺數上限


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
