"""求職總指揮：匯出求職檔案 Markdown。"""
from __future__ import annotations

from datetime import datetime

from ..models import ChatState, JobPreferences, MemoryState, ResumeState, Settings


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
