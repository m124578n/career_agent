from career_sentinel.models import Resume104
from career_sentinel.scraper import resume104


def _dur(y1, m1, y2, m2):
    return {"startYear": y1, "startMonth": m1, "endYear": y2, "endMonth": m2}


_PAYLOAD = {
    "data": {
        "resume": {"vno": "abc123"},
        "progress": 80,
        "sidebar": [{"id": "info", "completed": True}, {"id": "experience", "completed": True}],
        "ACData": {"info": {
            "name": "王小明", "email": "test@example.com", "cellphone": "0900000000",
            "city": [{"des": "台北市", "no": "1"}], "street": "測試路 1 號", "birthYear": 1998,
        }},
        "experience": {"formData": {"experiences": [{
            "companyName": "甲公司", "jobName": "後端工程師",
            "jobCat": [{"no": "1", "des": "軟體工程師"}],
            "duration": _dur(2020, 1, 2023, 6),
            "description": "負責 API 開發", "industry": [{"no": "2", "des": "軟體業"}],
        }]}},
        "education": {"formData": {"educations": [{
            "name": "測試大學", "departments": [{"name": "資工系", "type": "1"}],
            "highest": {"text": "學士", "value": 1}, "duration": _dur(2016, 9, 2020, 6),
            "status": {"text": "畢業", "value": 1},
        }]}},
        "skill": {"formData": {"skills": [{"name": "Python", "desc": "五年經驗", "tag": [{"text": "後端", "value": "1"}]}]}},
        "language": {"formData": {"languages": {"foreign": [{"type": {"text": "英文", "value": "1"}}]}}},
        "project": {"formData": {"projects": [{
            "name": "求職 agent", "duration": _dur(2024, 1, 2024, 6),
            "introduction": "本地求職工具", "url": "https://x",
        }]}},
        "bio": {"formData": {"bio": {"chi": "我是一位後端工程師…", "eng": ""}}},
    }
}


def test_parse_resume104_blocks():
    r = resume104.parse_resume104(_PAYLOAD)
    assert r.vno == "abc123" and r.progress == 80
    ids = [b.id for b in r.blocks]
    assert "info" in ids and "experience" in ids and "bio" in ids
    info = next(b for b in r.blocks if b.id == "info")
    assert info.is_pii is True and "王小明" in info.text and info.completed is True
    exp = next(b for b in r.blocks if b.id == "experience")
    assert exp.is_pii is False and "甲公司" in exp.text and "後端工程師" in exp.text and "2020" in exp.text
    edu = next(b for b in r.blocks if b.id == "education")
    assert "測試大學" in edu.text and "學士" in edu.text
    bio = next(b for b in r.blocks if b.id == "bio")
    assert "後端工程師" in bio.text


def test_parse_resume104_malformed_skips():
    assert resume104.parse_resume104({}).blocks == []
    assert resume104.parse_resume104({"data": {"experience": {"formData": {"experiences": [None, "x"]}}}}).vno == ""


def test_flatten_for_diagnosis_strips_pii():
    r = resume104.parse_resume104(_PAYLOAD)
    flat = resume104.flatten_for_diagnosis(r)
    # PII 不出現
    assert "王小明" not in flat and "test@example.com" not in flat and "0900000000" not in flat and "測試路" not in flat
    # 內容出現
    assert "甲公司" in flat and "後端工程師" in flat and "測試大學" in flat and "Python" in flat
