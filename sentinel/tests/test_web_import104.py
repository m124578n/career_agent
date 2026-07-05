from fastapi.testclient import TestClient
from career_sentinel import store
from career_sentinel.web import app as webapp


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def _mock_104(monkeypatch, session_ret):
    from career_sentinel.web import runner
    from career_sentinel.scraper import resume104
    monkeypatch.setattr(runner, "try_begin_browser", lambda: True)
    monkeypatch.setattr(runner, "end_browser", lambda: None)
    monkeypatch.setattr(resume104, "resume104_session", lambda: session_ret)


def _r104(pii_text="姓名：王小明", exp_text="甲公司 後端"):
    from career_sentinel.models import Resume104, Resume104Block
    return Resume104(vno="v1", progress=90, blocks=[
        Resume104Block(id="info", label="基本資料", text=pii_text, is_pii=True, completed=True),
        Resume104Block(id="experience", label="工作經歷", text=exp_text, is_pii=False, completed=True),
    ])


def test_import104_sets_active_resume_and_strips_pii(tmp_path, monkeypatch):
    _mock_104(monkeypatch, _r104())
    c = _client(tmp_path)
    r = c.post("/api/resume/import104")
    assert r.status_code == 200
    body = r.json()
    assert body["chars"] > 0
    assert body["resume104"]["vno"] == "v1"
    # resume_text 只含非 PII、source=104
    conn = store.connect(tmp_path / "db.sqlite")
    st = store.load_resume(conn)
    assert st.source == "104"
    assert "甲公司" in st.resume_text
    assert "王小明" not in st.resume_text  # PII 未進 resume_text
    g = c.get("/api/resume").json()
    assert g["has_resume"] is True and g["source"] == "104"


def test_import104_not_logged_in_409(tmp_path, monkeypatch):
    _mock_104(monkeypatch, None)
    assert _client(tmp_path).post("/api/resume/import104").status_code == 409


def test_import104_busy_409(tmp_path, monkeypatch):
    from career_sentinel.web import runner
    monkeypatch.setattr(runner, "try_begin_browser", lambda: False)
    assert _client(tmp_path).post("/api/resume/import104").status_code == 409


def test_import104_empty_after_strip_400(tmp_path, monkeypatch):
    # 全 PII → 攤平為空 → 400
    from career_sentinel.models import Resume104, Resume104Block
    _mock_104(monkeypatch, Resume104(vno="v1", progress=10, blocks=[
        Resume104Block(id="info", label="基本資料", text="姓名：王", is_pii=True, completed=True),
    ]))
    assert _client(tmp_path).post("/api/resume/import104").status_code == 400


def test_upload_sets_source_upload(tmp_path):
    c = _client(tmp_path)
    c.post("/api/resume/upload", files={"file": ("r.txt", "履歷內容".encode("utf-8"), "text/plain")})
    assert c.get("/api/resume").json()["source"] == "upload"


def test_resume_get_default_source_empty(tmp_path):
    assert _client(tmp_path).get("/api/resume").json()["source"] == ""
