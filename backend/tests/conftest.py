"""測試共用設定：讓測試不受開發者 .env 影響（停用認證 → dev 模式）。"""

import os

import pytest

from job_tracker.config import get_settings


@pytest.fixture(autouse=True, scope="session")
def _force_dev_settings():
    # 環境變數優先於 .env：清空 Google client id → 認證停用、dev@local 視為 admin
    os.environ["GOOGLE_CLIENT_ID"] = ""
    os.environ["ADMIN_EMAILS"] = ""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
