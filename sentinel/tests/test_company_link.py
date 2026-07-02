from career_sentinel.company_link import company_url_from_raw


def test_cust_url_protocol_relative():
    assert company_url_from_raw({"custUrl": "//www.104.com.tw/company/auxx12g"}) == \
        "https://www.104.com.tw/company/auxx12g"


def test_encoded_cust_no():
    assert company_url_from_raw({"custNo": "1a2x6blptx"}) == \
        "https://www.104.com.tw/company/1a2x6blptx"


def test_numeric_cust_no_unreliable():
    assert company_url_from_raw({"custNo": "97491093000"}) == ""


def test_empty_raw():
    assert company_url_from_raw({}) == ""


def test_cust_url_wins_over_cust_no():
    raw = {"custUrl": "//www.104.com.tw/company/abc", "custNo": "xyz9"}
    assert company_url_from_raw(raw) == "https://www.104.com.tw/company/abc"


def test_chat_url_from_chatroom_id():
    from career_sentinel.company_link import chat_url_from_raw
    assert chat_url_from_raw({"chatroomId": "8wtoc"}) == \
        "https://pda.104.com.tw/work/message/chat/8wtoc?page=1"
    assert chat_url_from_raw({}) == ""


def test_job_url_from_raw():
    from career_sentinel.company_link import job_url_from_raw
    assert job_url_from_raw({"jobUrl": "//www.104.com.tw/job/8jet3"}) == \
        "https://www.104.com.tw/job/8jet3"
    assert job_url_from_raw({"jobUrl": ""}) == ""
    assert job_url_from_raw({}) == ""
