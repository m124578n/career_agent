from __future__ import annotations

from .models import Settings


def is_watched(company: str, haystack: str, settings: Settings) -> bool:
    """命中任一關注公司（為 company 的不分大小寫子字串）或任一關鍵字（出現在 haystack）。"""
    company_l = (company or "").lower()
    for raw in settings.watched_companies:
        term = raw.strip().lower()
        if term and term in company_l:
            return True
    hay_l = (haystack or "").lower()
    for raw in settings.watched_keywords:
        term = raw.strip().lower()
        if term and term in hay_l:
            return True
    return False
