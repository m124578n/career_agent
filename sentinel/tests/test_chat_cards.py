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


def test_maybe_compact_prunes_orphan_card_results(tmp_path, monkeypatch):
    from career_sentinel import llm
    from career_sentinel.chat import memory as chatmem
    conn = store.connect(str(tmp_path / "db.sqlite"))
    # 舊訊息帶 card old1、最近訊息帶 card keep1；訊息數需 > COMPACT_THRESHOLD(30)
    msgs = [ChatMessage(role="user", content=f"m{i}") for i in range(30)]
    msgs[0] = ChatMessage(role="assistant", content="舊", suggestions=[
        SuggestedUpdate(field="research", op="run", payload={"company": "A"}, card_id="old1")])
    msgs.append(ChatMessage(role="assistant", content="新", suggestions=[
        SuggestedUpdate(field="research", op="run", payload={"company": "B"}, card_id="keep1")]))
    st = ChatState(messages=msgs, card_results={"old1": {"s": 1}, "keep1": {"s": 2}})
    monkeypatch.setattr(llm, "chat_stream",
                        lambda messages, *, system=None, client=None, feature="": iter(["摘要"]))
    new = chatmem.maybe_compact(conn, st)
    assert "keep1" in new.card_results
    assert "old1" not in new.card_results  # 被壓掉的訊息其卡結果一併清除
