from __future__ import annotations

import httpx

from .config import llm_settings
from .models import Diff, Snapshot


def build_prompt(diff: Diff, snapshot: Snapshot) -> str:
    lines: list[str] = ["以下是使用者 104 求職狀態自上次以來的變化，請用繁體中文寫一段精簡的今日彙整："]
    if diff.new_viewers:
        lines.append("\n[新看過我的公司]")
        lines += [f"- {v.company}（{v.job_title}）{v.viewed_at}" for v in diff.new_viewers]
    if diff.status_changes:
        lines.append("\n[投遞狀態變動]")
        lines += [f"- {c.application.company} {c.application.title}：{c.old_status} → {c.new_status}" for c in diff.status_changes]
    if diff.new_messages:
        lines.append("\n[新訊息]")
        lines += [f"- {m.company}：{m.last_message}" for m in diff.new_messages]
    if diff.new_invites:
        lines.append("\n[面試邀約]")
        lines += [f"- {m.company}（邀約日期：{m.invite_date or '未定'}）" for m in diff.new_invites]
    lines.append(f"\n目前共投遞 {len(snapshot.applications)} 筆、累計 {len(snapshot.viewers)} 家看過你。")
    return "\n".join(lines)


def _local_fallback(diff: Diff, snapshot: Snapshot) -> str:
    if diff.is_empty():
        return "今日沒有新變化。"
    return build_prompt(diff, snapshot)


def summarize(diff: Diff, snapshot: Snapshot, *, client: object | None = None) -> str:
    cfg = llm_settings()
    if diff.is_empty() or not cfg.api_key:
        return _local_fallback(diff, snapshot)

    http = client or httpx.Client(timeout=60)
    resp = http.post(
        f"{cfg.base_url}/chat/completions",
        headers={"Authorization": f"Bearer {cfg.api_key}"},
        json={
            "model": cfg.model,
            "messages": [{"role": "user", "content": build_prompt(diff, snapshot)}],
        },
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
