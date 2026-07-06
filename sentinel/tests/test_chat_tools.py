import json

from career_sentinel import chat
from career_sentinel.models import RecommendedJob


class _Blk:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeFinal:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class _FakeStream:
    def __init__(self, texts, final):
        self.text_stream = iter(texts)
        self._final = final

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self._final


class _FakeMessages:
    def __init__(self, turns):
        self._turns = list(turns)  # [(texts, final), ...]
        self.captured = []

    def stream(self, **kw):
        self.captured.append(kw)
        texts, final = self._turns.pop(0)
        return _FakeStream(texts, final)


class _FakeClient:
    def __init__(self, turns):
        self.messages = _FakeMessages(turns)


def _jobs(n):
    return [RecommendedJob(code=f"c{i}", url=f"https://www.104.com.tw/job/c{i}",
                           title=f"職缺{i}", company=f"公司{i}", salary="月薪 5萬") for i in range(n)]


def test_stream_with_tools_happy_path(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    monkeypatch.setattr(chat, "_execute_search",
                        lambda kw: (_jobs(2), json.dumps([{"title": "職缺0"}]), False))
    tool_use = _Blk("tool_use", id="tu1", name="search_jobs", input={"keyword": "python 後端"})
    client = _FakeClient([
        (["我來搜尋"], _FakeFinal("tool_use", [_Blk("text", text="我來搜尋"), tool_use])),
        (["找到了，前兩筆不錯"], _FakeFinal("end_turn", [_Blk("text", text="找到了，前兩筆不錯")])),
    ])
    evs = list(chat.stream_with_tools(
        [{"role": "user", "content": "幫我找 python 後端"}], system="s", client=client))
    kinds = [e["type"] for e in evs]
    assert kinds == ["text", "jobs", "text"]
    assert evs[1]["keyword"] == "python 後端" and len(evs[1]["items"]) == 2
    # 第一輪帶 tools；第二輪 tool_runs=1 < 2 仍帶
    assert "tools" in client.messages.captured[0]
    assert "tools" in client.messages.captured[1]
    # 第二輪 messages 追加 assistant(content=final.content) + user(tool_result)
    msgs2 = client.messages.captured[1]["messages"]
    assert msgs2[-2]["role"] == "assistant"
    assert msgs2[-1]["role"] == "user"
    assert msgs2[-1]["content"][0]["type"] == "tool_result"
    assert msgs2[-1]["content"][0]["tool_use_id"] == "tu1"
    # system 有注入今天日期
    assert "今天日期：" in client.messages.captured[0]["system"]


def test_stream_with_tools_loop_limit(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    monkeypatch.setattr(chat, "_execute_search", lambda kw: ([], "[]", False))
    def tu(i):
        return _Blk("tool_use", id=f"tu{i}", name="search_jobs", input={"keyword": f"k{i}"})
    client = _FakeClient([
        ([], _FakeFinal("tool_use", [tu(1)])),
        ([], _FakeFinal("tool_use", [tu(2)])),
        (["只好用現有結果回答"], _FakeFinal("end_turn", [_Blk("text", text="只好用現有結果回答")])),
    ])
    list(chat.stream_with_tools([{"role": "user", "content": "找"}], system="s", client=client))
    cap = client.messages.captured
    assert "tools" in cap[0] and "tools" in cap[1]
    assert "tools" not in cap[2]  # 達上限，最後一輪強制作答


def test_stream_with_tools_error_no_jobs_event(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    monkeypatch.setattr(chat, "_execute_search", lambda kw: ([], "搜尋失敗：boom", True))
    tool_use = _Blk("tool_use", id="tu1", name="search_jobs", input={"keyword": "x"})
    client = _FakeClient([
        ([], _FakeFinal("tool_use", [tool_use])),
        (["抱歉搜尋失敗"], _FakeFinal("end_turn", [_Blk("text", text="抱歉搜尋失敗")])),
    ])
    evs = list(chat.stream_with_tools([{"role": "user", "content": "找"}], system="s", client=client))
    assert [e["type"] for e in evs] == ["text"]  # 無 jobs 事件
    tr = client.messages.captured[1]["messages"][-1]["content"][0]
    assert tr.get("is_error") is True


def test_execute_search_limits_and_error(monkeypatch):
    from career_sentinel.scraper import search as search_mod
    monkeypatch.setattr(search_mod, "fetch_search", lambda kw: _jobs(10))
    jobs, text, is_error = chat._execute_search("python")
    assert len(jobs) == 10 and is_error is False
    brief = json.loads(text)
    assert len(brief) == 8  # JOBS_RESULT_LIMIT
    assert set(brief[0].keys()) == {"title", "company", "salary", "url"}

    def boom(kw):
        raise RuntimeError("104 掛了")
    monkeypatch.setattr(search_mod, "fetch_search", boom)
    jobs2, text2, is_error2 = chat._execute_search("python")
    assert jobs2 == [] and is_error2 is True and "搜尋失敗" in text2


def test_system_prompt_mentions_tool_rules():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState())
    assert "search_jobs" in p and "get_pipeline" in p


def test_execute_search_empty_keyword_is_error():
    jobs, text, is_error = chat._execute_search("  ")
    assert jobs == [] and is_error is True and "關鍵字為空" in text


def test_format_pipeline_summary_groups_and_counts():
    from career_sentinel.models import OfferDetail, PipelineJob
    jobs = [
        PipelineJob(key="a", code="a", company="甲", title="後端", state="offer",
                    offer=OfferDetail(salary_year=1200000)),
        PipelineJob(key="b", code="b", company="乙", title="前端", state="interviewing",
                    when="2026-07-10 14:00:00"),
        PipelineJob(key="c", code="c", company="丙", title="PM", state="interested"),
    ]
    s = chat.format_pipeline_summary(jobs)
    assert "offer" in s and "甲" in s and "1200000" in s
    assert "乙" in s and "2026-07-10" in s
    assert "（a）" in s  # code 供 agent 引用


def test_format_pipeline_summary_empty():
    assert chat.format_pipeline_summary([]) == ""


def test_format_pipeline_summary_group_limit():
    from career_sentinel.models import PipelineJob
    jobs = [PipelineJob(key=str(i), code=str(i), company=f"公司{i}", title="x", state="interested")
            for i in range(8)]
    s = chat.format_pipeline_summary(jobs)
    assert "8 筆" in s              # 計數顯示全部 8 筆
    assert "公司0" in s and "公司4" in s and "公司5" not in s  # 只列前 5 筆


def test_system_prompt_includes_pipeline_summary():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState(), "【管道摘要文字】")
    assert "目前求職管道" in p and "【管道摘要文字】" in p


def test_system_prompt_empty_pipeline_shows_placeholder():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState(), "")
    assert "管道目前無職缺" in p


def test_contract_mentions_pipeline_actions():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState())
    for f in ("track", "job_offer", "job_reject", "job_reset", "untrack"):
        assert f in p
