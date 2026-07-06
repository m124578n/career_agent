from career_sentinel import chat
from career_sentinel.models import (
    ChatMessage, ChatState, JobPreferences, MemoryFact, MemoryState, ResumeState, Settings,
)


def test_system_prompt_embeds_state():
    p = chat.build_system_prompt(
        ResumeState(resume_text="Python 五年"),
        Settings(watched_companies=["台積電"], watched_keywords=["Python"]),
        JobPreferences(target_title="後端工程師", expected_salary=900000,
                       locations=["台北"], conditions=["可遠端"], avoid=["博弈"]),
        MemoryState(facts=[MemoryFact(text="通勤以雙北為主")]),
    )
    for needle in ("後端工程師", "900000", "台積電", "台北", "可遠端", "博弈",
                   "通勤以雙北為主", "Python 五年", "<suggestions>"):
        assert needle in p


def test_build_messages_with_summary_and_history():
    state = ChatState(summary="聊過薪資", messages=[
        ChatMessage(role="user", content="a"), ChatMessage(role="assistant", content="b"),
    ])
    msgs = chat.build_messages(state, "c")
    assert msgs[0]["role"] == "user" and "聊過薪資" in msgs[0]["content"]
    assert msgs[1]["role"] == "assistant"  # 摘要後補 assistant 回應，維持角色交替
    assert msgs[2:] == [
        {"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ]


def test_build_messages_no_summary():
    msgs = chat.build_messages(ChatState(), "hi")
    assert msgs == [{"role": "user", "content": "hi"}]


def test_stream_filter_plain_text_passthrough():
    f = chat.StreamFilter()
    out = f.feed("你好") + f.feed("！") + f.finish()
    assert out == "你好！"
    assert f.tail() == ""


def test_stream_filter_cuts_suggestions_block():
    f = chat.StreamFilter()
    out = f.feed("好的<suggestions>{\"items\":[]}") + f.feed("</suggestions>") + f.finish()
    assert out == "好的"
    assert f.tail() == "<suggestions>{\"items\":[]}</suggestions>"


def test_stream_filter_marker_split_across_chunks():
    f = chat.StreamFilter()
    out = f.feed("好的<sugg") + f.feed("estions>{}")
    out += f.finish()
    assert out == "好的"
    assert f.tail() == "<suggestions>{}"


def test_stream_filter_false_partial_marker_released_at_finish():
    f = chat.StreamFilter()
    out = f.feed("小於符號 <sugg")  # 不是標記、只是像
    out += f.finish()
    assert out == "小於符號 <sugg"


def test_parse_suggestions_valid():
    tail = '<suggestions>{"items":[{"field":"expected_salary","op":"set","value":900000}]}</suggestions>'
    items = chat.parse_suggestions(tail)
    assert len(items) == 1
    assert items[0].field == "expected_salary" and items[0].value == 900000


def test_parse_suggestions_bad_json_returns_empty():
    assert chat.parse_suggestions("<suggestions>{oops</suggestions>") == []
    assert chat.parse_suggestions("") == []
    assert chat.parse_suggestions("<suggestions>{\"items\": \"not-a-list\"}</suggestions>") == []
