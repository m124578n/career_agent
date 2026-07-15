"""求職總指揮：系統提示與訊息組裝。"""
from __future__ import annotations

from datetime import datetime

from ..models import ChatState, JobPreferences, MemoryState, PipelineJob, ResumeState, Settings

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
  {"field": "interview_note", "op": "set", "payload": {"code": "abc12", "when": "2026-07-10 14:00 一面", "content": "問了系統設計與過往專案"}},
  {"field": "interview_prep", "op": "run", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師"}},
  {"field": "research", "op": "run", "payload": {"company": "華碩"}}
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
- 面試準備（interview_prep/run）：使用者面試前想準備某職缺（想知道可能考題、怎麼準備）時，提議
  {"field": "interview_prep", "op": "run", "payload": {"code": "...", "company": "...", "title": "..."}}.
  需使用者已上傳履歷；payload.code 必來自 get_pipeline/search_jobs 的實際結果、不得杜撰。
  這是**提議**，會等使用者按下才實際生成（花 LLM 錢；深度模式還會網搜）——你不要自行寫面試題或聲稱已完成，只丟提議卡。
- 查公司評價（research/run）：使用者想了解某公司風評／值不值得去／評價時，提議
  {"field": "research", "op": "run", "payload": {"company": "公司名"}}.
  company 取自對話或管道中的公司名、不得杜撰。這是**提議**，等使用者按下才實際上網查
  （花 LLM 錢＋web search）——**你不要自行編造公司評價或聲稱已查**，只丟提議卡。
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
        "fetch_url 讀任意網址內容（使用者貼網址要你看/分析職缺時用；非 104 站也可）；"
        "salary_insights 查某職稱/關鍵字的 104 薪資行情（談薪資或討論 offer 時可用）；"
        "工具呼叫請節制。\n\n"
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
