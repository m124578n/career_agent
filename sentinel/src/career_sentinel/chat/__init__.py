"""求職總指揮服務層：prompt 組裝、建議解析/套用、compact/記憶整理、工具執行、tool-use 編排。

實作拆到子模組（prompt/suggestions/memory/export/tools/orchestrator）；此處再匯出公開面，
維持 `from career_sentinel import chat` 後 `chat.X` 的既有存取（含被測試 monkeypatch 的私有函式）。
"""
from __future__ import annotations

from .. import llm  # noqa: F401 — 對外相容：chat.llm
from .export import build_export_md  # noqa: F401
from .memory import (  # noqa: F401
    COMPACT_KEEP, COMPACT_THRESHOLD, CURATE_THRESHOLD, CuratedFacts,
    maybe_compact, maybe_curate_memory,
)
from .orchestrator import TOOL_LOOP_MAX, stream_with_tools  # noqa: F401
from .prompt import build_messages, build_system_prompt, format_pipeline_summary  # noqa: F401
from .suggestions import ApplyResult, StreamFilter, apply_update, parse_suggestions  # noqa: F401
from .tools import (  # noqa: F401
    JOBS_RESULT_LIMIT, TOOLS, _FETCH_URL_MAX, _JD_DESC_MAX,
    _execute_fetch_url, _execute_job_detail, _execute_salary_insights, _execute_search,
    _execute_tool, _html_to_text, _pipeline_tool_json,
)
