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


def test_match_result_score_clamped_high():
    from career_sentinel.models import MatchResult
    assert MatchResult(score=120).score == 100


def test_match_result_score_clamped_low():
    from career_sentinel.models import MatchResult
    assert MatchResult(score=-5).score == 0


def test_match_result_score_from_float_and_garbage():
    from career_sentinel.models import MatchResult
    assert MatchResult(score=85.7).score == 86
    assert MatchResult(score="not a number").score == 0
