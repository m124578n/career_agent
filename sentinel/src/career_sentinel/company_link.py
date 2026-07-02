"""從 104 raw payload 取公司頁連結。

爬蟲當下就把每筆的 raw 全量入庫，這裡從 raw 抽出真正的公司頁網址：
- applications 的 `custUrl`（protocol-relative，補 https:）
- viewers/interviews 的 encoded `custNo`（組 /company/{custNo}）
- messages 的 custNo 是純數字、組不出可靠公司頁 → 回空字串，由前端 fallback 公司搜尋頁。
"""
from __future__ import annotations

_COMPANY_BASE = "https://www.104.com.tw/company/"


def _norm_url(u: str) -> str:
    return "https:" + u if u.startswith("//") else u


def company_url_from_raw(raw: dict) -> str:
    cust_url = str(raw.get("custUrl") or "")
    if "104.com.tw/company/" in cust_url:
        return _norm_url(cust_url)
    cust_no = str(raw.get("custNo") or "")
    if cust_no and not cust_no.isdigit():  # encoded 代碼含字母；純數字不可靠
        return _COMPANY_BASE + cust_no
    return ""


_CHAT_BASE = "https://pda.104.com.tw/work/message/chat"


def chat_url_from_raw(raw: dict) -> str:
    """訊息/面試的 104 聊天室連結（chatroomId 爬蟲當下即入庫）。"""
    cid = str(raw.get("chatroomId") or "")
    return f"{_CHAT_BASE}?chatroomId={cid}" if cid else ""


def job_url_from_raw(raw: dict) -> str:
    """應徵的職缺頁連結（raw.jobUrl，protocol-relative 補 https:）。"""
    u = str(raw.get("jobUrl") or "")
    return _norm_url(u) if "104.com.tw/job/" in u else ""
