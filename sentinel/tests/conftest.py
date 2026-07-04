"""測試共用設定。

自動把每個測試的資料目錄導向臨時目錄，避免測試（例如未 mock usage.record 的
真 LLM 函式呼叫，會經 config.db_path() 寫入 usage_log）污染使用者真實的
sentinel/data/sentinel.db。明確自建 db 的測試（create_app(db_path=…)、
store.connect(tmp)）不受影響。
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
