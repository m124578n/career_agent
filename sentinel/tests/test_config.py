from career_sentinel import config


def test_data_dir_honours_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    assert config.data_dir() == tmp_path
    assert config.profile_dir() == tmp_path / "chrome-profile"
    assert config.db_path() == tmp_path / "sentinel.db"


def test_llm_settings_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://x/v1")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    s = config.llm_settings()
    assert (s.base_url, s.api_key, s.model) == ("https://x/v1", "k", "m")
