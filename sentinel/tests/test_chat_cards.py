from career_sentinel import store
from career_sentinel.chat import prompt as chatprompt
from career_sentinel.models import ChatMessage, ChatState, SuggestedUpdate


def test_chat_state_roundtrip_keeps_suggestions_and_card_results(tmp_path):
    conn = store.connect(str(tmp_path / "db.sqlite"))
    st = ChatState(
        messages=[
            ChatMessage(role="user", content="這間華碩如何"),
            ChatMessage(role="assistant", content="我可以幫你查", suggestions=[
                SuggestedUpdate(field="research", op="run",
                                payload={"company": "華碩"}, card_id="cid1"),
            ]),
        ],
        card_results={"cid1": {"summary": "毀譽參半", "risk_level": "mid"}},
    )
    store.save_chat(conn, st)
    got = store.load_chat(conn)
    assert got.messages[1].suggestions[0].card_id == "cid1"
    assert got.messages[1].suggestions[0].field == "research"
    assert got.card_results["cid1"]["risk_level"] == "mid"


def test_build_messages_excludes_suggestions_and_card_results(tmp_path):
    st = ChatState(
        messages=[
            ChatMessage(role="assistant", content="我可以幫你查", suggestions=[
                SuggestedUpdate(field="research", op="run",
                                payload={"company": "華碩"}, card_id="cid1"),
            ]),
        ],
        card_results={"cid1": {"summary": "機密評價內容不該進 prompt"}},
    )
    msgs = chatprompt.build_messages(st, "下一步")
    blob = repr(msgs)
    assert "機密評價內容不該進 prompt" not in blob
    assert "cid1" not in blob
    assert "research" not in blob
    assert all(set(m.keys()) == {"role", "content"} for m in msgs)
