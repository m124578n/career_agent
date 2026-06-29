from career_sentinel.models import JobDetail, MatchResult


def test_jobdetail_defaults():
    jd = JobDetail()
    assert jd.title == "" and jd.majors == [] and jd.specialties == []


def test_matchresult_construct():
    m = MatchResult(score=80, reasons=["熟 Python"], gaps=["缺雲端"])
    assert m.score == 80 and m.reasons == ["熟 Python"] and m.gaps == ["缺雲端"]


def test_matchresult_defaults():
    m = MatchResult()
    assert m.score == 0 and m.reasons == [] and m.gaps == []
