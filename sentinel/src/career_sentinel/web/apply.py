"""SP11b 半自動投遞：用登入態純 Chrome 開職缺頁供使用者親手應徵。

不 POST、不填表、不碰 104 投遞 API——只 subprocess 開一個網址（同 cli login 機制）。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .. import browser, config


def open_job_page(job_url: str) -> bool:
    """用專案 profile（登入態）的純 Chrome 開職缺頁。找不到 Chrome 回 False。"""
    chrome = browser.find_chrome()
    if not chrome:
        return False
    profile = config.profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            chrome,
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--",
            job_url,
        ]
    )
    return True
