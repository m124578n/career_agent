"""M6 外部投遞偵測：判斷職缺是否要求至公司官網投遞，若是則標記提醒（不自動處理）。"""

import re

# 常見「請至官網/外部連結投遞」的關鍵字
_EXTERNAL_HINTS = [
    "請至", "官網投遞", "公司官網", "外部連結", "請上",
    "company website", "apply on", "external",
]


def requires_external_apply(description: str) -> bool:
    """規則判斷職缺是否要求外部投遞。"""
    text = description.lower()
    return any(hint.lower() in text for hint in _EXTERNAL_HINTS) or bool(
        re.search(r"https?://(?!www\.104)", description)
    )
