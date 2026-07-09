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
from .tools import (  # noqa: F401
    JOBS_RESULT_LIMIT, TOOLS, _FETCH_URL_MAX, _JD_DESC_MAX,
    _execute_fetch_url, _execute_job_detail, _execute_search, _execute_tool,
    _html_to_text, _pipeline_tool_json,
)

TOOL_LOOP_MAX = 4       # 每輪對話最多執行幾次工具


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
