from __future__ import annotations

from ..models import Resume104, Resume104Block

RESUME_LIST_URL = "https://pda.104.com.tw/profile/ajax/completeResumeList?top=isMaster"
RESUME_BLOCK_URL = "https://pda.104.com.tw/profile/ajax/resumeByBlock?vno={vno}"

_LABELS = {
    "info": "基本資料", "experience": "工作經歷", "education": "學歷",
    "skill": "技能", "language": "語言", "project": "專案", "bio": "自傳",
}
# 內容區塊（非 PII）——健檢用
_CONTENT = ["experience", "education", "skill", "language", "project", "bio"]


def _s(v) -> str:
    return str(v).strip() if v is not None else ""


def _d(v) -> dict:
    """安全取 dict：非 dict 回空 dict（防 104 回傳非預期形狀）。"""
    return v if isinstance(v, dict) else {}


def _dur(d) -> str:
    if not isinstance(d, dict):
        return ""
    sy, sm = d.get("startYear"), d.get("startMonth")
    ey, em = d.get("endYear"), d.get("endMonth")
    start = f"{sy}/{sm}" if sy else ""
    end = f"{ey}/{em}" if ey else "至今"
    return f"{start} ~ {end}".strip(" ~") if start or ey else ""


def _des_join(lst) -> str:
    if not isinstance(lst, list):
        return ""
    return "、".join(_s(x.get("des")) for x in lst if isinstance(x, dict) and x.get("des"))


def _flatten_info(data: dict) -> str:
    info = _d(_d(data.get("ACData")).get("info"))
    city = _des_join(info.get("city"))
    parts = [
        f"姓名：{_s(info.get('name'))}",
        f"Email：{_s(info.get('email'))}",
        f"手機：{_s(info.get('cellphone'))}",
        f"居住地：{city} {_s(info.get('street'))}".strip(),
    ]
    return "\n".join(p for p in parts if p.split("：", 1)[-1].strip())


def _flatten_experience(fd: dict) -> str:
    out = []
    for e in fd.get("experiences") or []:
        if not isinstance(e, dict):
            continue
        head = f"{_s(e.get('companyName'))}｜{_s(e.get('jobName'))}（{_dur(e.get('duration'))}）"
        lines = [head]
        cat = _des_join(e.get("jobCat"))
        if cat:
            lines.append(f"職類：{cat}")
        if _s(e.get("description")):
            lines.append(_s(e.get("description")))
        out.append("\n".join(lines))
    return "\n\n".join(out)


def _flatten_education(fd: dict) -> str:
    out = []
    for e in fd.get("educations") or []:
        if not isinstance(e, dict):
            continue
        dep = "、".join(_s(x.get("name")) for x in (e.get("departments") or []) if isinstance(x, dict))
        highest = _s(_d(e.get("highest")).get("text"))
        status = _s(_d(e.get("status")).get("text"))
        out.append(f"{_s(e.get('name'))} {dep} {highest}（{_dur(e.get('duration'))}）{status}".strip())
    return "\n".join(out)


def _flatten_skill(fd: dict) -> str:
    out = []
    for s in fd.get("skills") or []:
        if not isinstance(s, dict):
            continue
        name = _s(s.get("name"))
        desc = _s(s.get("desc"))
        out.append(f"{name}：{desc}" if desc else name)
    return "\n".join(x for x in out if x)


def _flatten_language(fd: dict) -> str:
    langs = _d(fd.get("languages"))
    out = []
    for f in langs.get("foreign") or []:
        if isinstance(f, dict):
            out.append(_s(_d(f.get("type")).get("text")))
    return "、".join(x for x in out if x)


def _flatten_project(fd: dict) -> str:
    out = []
    for p in fd.get("projects") or []:
        if not isinstance(p, dict):
            continue
        head = f"{_s(p.get('name'))}（{_dur(p.get('duration'))}）"
        intro = _s(p.get("introduction"))
        out.append(f"{head}\n{intro}" if intro else head)
    return "\n\n".join(out)


def _flatten_bio(fd: dict) -> str:
    bio = fd.get("bio")
    if not isinstance(bio, dict):
        return ""
    return _s(bio.get("chi")) or _s(bio.get("eng"))


_FLATTEN = {
    "experience": _flatten_experience, "education": _flatten_education,
    "skill": _flatten_skill, "language": _flatten_language,
    "project": _flatten_project, "bio": _flatten_bio,
}


def parse_resume104(payload: dict) -> Resume104:
    data = payload.get("data")
    if not isinstance(data, dict):
        return Resume104()
    vno = _s(_d(data.get("resume")).get("vno"))
    progress = data.get("progress") if isinstance(data.get("progress"), int) else 0
    sidebar = {
        _s(s.get("id")): bool(s.get("completed"))
        for s in (data.get("sidebar") or []) if isinstance(s, dict)
    }
    blocks: list[Resume104Block] = []
    info_text = _flatten_info(data)
    if info_text:
        blocks.append(Resume104Block(id="info", label=_LABELS["info"], text=info_text,
                                      is_pii=True, completed=sidebar.get("info", False)))
    for bid in _CONTENT:
        fd = _d(_d(data.get(bid)).get("formData"))
        text = _FLATTEN[bid](fd)
        if text.strip():
            blocks.append(Resume104Block(id=bid, label=_LABELS[bid], text=text,
                                         is_pii=False, completed=sidebar.get(bid, False)))
    return Resume104(vno=vno, progress=progress, blocks=blocks)


def flatten_for_diagnosis(r: Resume104) -> str:
    """健檢用文字：只取非 PII 區塊，含區塊標題。"""
    return "\n\n".join(
        f"【{b.label}】\n{b.text}" for b in r.blocks if not b.is_pii and b.text.strip()
    )


_PROFILE_PAGE = "https://pda.104.com.tw/my/resume/list"


def fetch_resume104(page) -> Resume104:
    """需已登入且已取得 pda host clearance。需真瀏覽器、不單測。"""
    lst = page.request.get(RESUME_LIST_URL)
    if not lst.ok:
        raise RuntimeError(f"resume list HTTP {lst.status}")
    raw = lst.json()
    data = raw.get("data") if isinstance(raw, dict) else None
    items = data if isinstance(data, list) else []
    vno = ""
    for r in items:
        if isinstance(r, dict) and r.get("vno"):
            vno = str(r.get("vno"))
            if r.get("isMaster") or r.get("master"):
                break
    if not vno:
        import logging
        logging.getLogger("career_sentinel").warning(
            "resume104 無 vno：status=%s top_keys=%s body=%s",
            lst.status,
            sorted(raw.keys()) if isinstance(raw, dict) else type(raw).__name__,
            (lst.text() or "")[:500],
        )
        raise RuntimeError("找不到履歷 vno（104 履歷 API 結構可能已變更，已記錄回應供修正）")
    blk = page.request.get(RESUME_BLOCK_URL.format(vno=vno))
    if not blk.ok:
        raise RuntimeError(f"resumeByBlock HTTP {blk.status}")
    return parse_resume104(blk.json())


def resume104_session() -> Resume104 | None:
    """開 headful context → 導覽 pda 履歷頁取 clearance + 確認登入 → 讀履歷。未登入回 None。"""
    from rebrowser_playwright.sync_api import sync_playwright

    from .. import browser

    with sync_playwright() as p:
        ctx = browser.open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(_PROFILE_PAGE, wait_until="domcontentloaded")
            browser.wait_until_ready(page)
            if browser.is_login_url(page.url):
                return None
            return fetch_resume104(page)
        finally:
            ctx.close()
