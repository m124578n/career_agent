"""集中 logging 設定。輸出到 stdout，Zeabur 等平台會自動收集。"""

import logging

from job_tracker.config import get_settings

_configured = False


def setup_logging() -> None:
    """配置 root logger（冪等）。level 由 LOG_LEVEL 環境變數控制。"""
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=get_settings().log_level.upper(),
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    _configured = True
