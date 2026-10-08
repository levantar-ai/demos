"""What the model is told, what it is given, and how its choices are recorded.

None of this calls Bedrock. The agent and the model are replaced with fakes
that record how they were built, which is the part of model.py that carries
the security claims: the customer id reaches the model as text, the token
reaches the gateway client as a header, and the two never cross.
"""

import json
import os
from typing import ClassVar

import gateway
import handoff
import memory
import model
import pytest
import sandbox
import trail as trail_module

os.environ.update({
    "MODEL_ID": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "GATEWAY_URL": "https://gw.example/mcp",
    "MEMORY_ID": "mem-test",
    "CODE_INTERPRETER_ID": "ci-test",
    "AWS_REGION": "us-east-1",
})


class FakeModel:
    def __init__(self, **kw):
        self.kw = kw


class FakeManager:
    def __init__(self, config, region_name=None):
        self.config = config
        self.region_name = region_name
        self.closed = False

    def close(self):
        self.closed = True


class FakeClient:
    """Lifecycle-aware stand-in: Strands starts the real client while the
    agent is built, so the fake is 'started' as soon as the agent sees it."""

    def __init__(self, **kw):
        self.kw = kw
        self.started = False
        self.stopped = 0

    def stop(self, exc_type, exc_val, exc_tb):
        """Same signature as strands MCPClient.stop, which has no defaults;
        a closer that calls it without arguments is a bug the live log
        showed as 'cleanup failed' on every turn."""
        if self.started:
            self.stopped += 1
            self.started = False


class FakeResult:
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return self.text


class FakeAgent:
    built: ClassVar[list] = []
    restored_messages: ClassVar[list] = []
    runs_python: ClassVar[bool] = False  # when set, the fake model calls run_python once

    def __init__(self, **kw):
        self.kw = kw
        self.messages = list(FakeAgent.restored_messages)
        self.cleaned = False
        for t in kw.get("tools", []):
            if isinstance(t, FakeClient):
                t.started = True
        FakeAgent.built.append(self)

    def __call__(self, prompt):
        self.prompt = prompt
        if FakeAgent.runs_python:
            run = next(t for t in self.kw["tools"] if getattr(t, "tool_name", None) == "run_python")
            self.ran = run(code="print(1)")
        return FakeResult(f"answered: {prompt}")

    def cleanup(self):
        self.cleaned = True
        for t in self.kw.get("tools", []):
            if isinstance(t, FakeClient):
                t.stop(None, None, None)


def _answer(*args):
    turn = model.answer(*args)
    return turn["result"], turn["trail"], turn["unsupported_figures"]


@pytest.fixture
def fakes(monkeypatch):
    FakeAgent.built.clear()
    monkeypatch.setattr(model, "make_model", FakeModel)
    monkeypatch.setattr(model, "make_agent", FakeAgent)
    monkeypatch.setattr(gateway, "make_client", FakeClient)
    monkeypatch.setattr(memory, "make_manager", FakeManager)
    monkeypatch.setattr(sandbox.Sandbox, "stop", staticmethod(lambda interpreter, sid: None))
    return FakeAgent


def test_the_model_is_told_the_date_by_trusted_code(fakes, monkeypatch):
    """'This year' has to mean something; the live run showed the model
    grouping every order when the fixture happened to be one year."""
    monkeypatch.setattr(model, "today", lambda: "2026-10-07")
    model.answer("spent this year?", "c-1000", "session-1", "minted-token", "sub-1000")
    prompt = fakes.built[-1].kw["system_prompt"]
    assert "Today is 2026-10-07 (UTC)" in prompt and '"this year" means the calendar year of that date' in prompt


def test_the_restored_conversation_is_windowed(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token", "sub-1000")
    manager = fakes.built[-1].kw["conversation_manager"]
    assert manager.window_size == model.WINDOW_MESSAGES
    # sliding, not truncating: the default would blank the latest tool
    # results of an overfull conversation before trimming anything
    assert manager.should_truncate_results is False


def _filler(n):
    return [{"role": ("user", "assistant")[i % 2], "content": [{"text": f"m{i}"}]} for i in range(n)]


def test_the_window_is_applied_before_restore_scans_the_conversation(fakes, monkeypatch):
    """What restore() scans is what the model is shown: a gateway result
    that has slid out of the window is not restored, one inside it is."""
    staged = []
    monkeypatch.setattr(sandbox.Sandbox, "stage", lambda self, path, text: staged.append(path))
    monkeypatch.setattr(FakeAgent, "restored_messages", _conversation_with_a_fetch("rows") + _filler(model.WINDOW_MESSAGES))
    model.answer("hello", "c-1000", "session-1", "minted-token", "sub-1000")
    assert staged == []
    assert len(fakes.built[-1].messages) <= model.WINDOW_MESSAGES
    monkeypatch.setattr(FakeAgent, "restored_messages", _filler(model.WINDOW_MESSAGES - 6) + _conversation_with_a_fetch("rows"))
    model.answer("hello", "c-1000", "session-1", "minted-token", "sub-1000")
    assert staged == ["orders.json"]
    assert len(fakes.built[-1].messages) == model.WINDOW_MESSAGES


def test_tools_run_one_at_a_time_in_the_order_the_model_asked(fakes):
    from strands.tools.executors import SequentialToolExecutor

    model.answer("my orders", "c-1000", "session-1", "minted-token", "sub-1000")
    assert isinstance(fakes.built[-1].kw["tool_executor"], SequentialToolExecutor)


def test_the_model_learns_the_customer_from_trusted_code(fakes):
    text, steps, _ = _answer("how much have I spent?", "c-1000", "session-1", "minted-token", "sub-1000")
    agent = fakes.built[-1]
    assert text == "answered: how much have I spent?"
    assert steps == []
    assert "c-1000" in agent.kw["system_prompt"]
    assert "c-1001" not in agent.kw["system_prompt"]


def test_the_model_is_told_the_gateway_is_the_only_source_of_orders(fakes):
    """The live run's lesson: without this the second turn of a conversation
    invented a dataset in the sandbox instead of fetching again."""
    model.answer("which carrier?", "c-1000", "session-1", "minted-token", "sub-1000")
    prompt = fakes.built[-1].kw["system_prompt"]
    assert "only source of order data" in prompt
    assert "Never invent" in prompt
    assert "call it again" in prompt  # a restored snapshot is for analysis, not for current status
    assert "Call it in any turn that needs order data" not in prompt  # reuse is allowed for the same figures
    assert "there is no suitable result from earlier in this conversation" in prompt
    assert "current status, carrier or ETA of an order" in prompt


def test_the_token_goes_to_the_gateway_client_and_never_to_the_model(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token", "sub-1000")
    agent = fakes.built[-1]
    client = next(t for t in agent.kw["tools"] if isinstance(t, FakeClient))
    assert client.kw == {
        "url": "https://gw.example/mcp",
        "headers": {"Authorization": "Bearer minted-token"},
        "tool_filters": {"allowed": ["orders___list_orders"]},
    }
    assert "minted-token" not in agent.kw["system_prompt"]


def test_only_the_allowlisted_gateway_tools_reach_the_model(fakes):
    """A target added to the gateway later is not handed to the model until
    it is named in the agent."""
    model.answer("my orders", "c-1000", "session-1", "minted-token", "sub-1000")
    client = next(t for t in fakes.built[-1].kw["tools"] if isinstance(t, FakeClient))
    assert client.kw["tool_filters"]["allowed"] == ["orders___list_orders"]


def test_the_model_is_given_the_sandbox_as_a_tool(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token", "sub-1000")
    agent = fakes.built[-1]
    names = [getattr(t, "tool_name", None) for t in agent.kw["tools"]]
    assert "run_python" in names


def test_memory_is_keyed_by_the_tokens_subject_and_the_session(fakes):
    """The customer id the model is told is the username; the memory's actor
    is the subject, which a recreated username does not inherit."""
    model.answer("my orders", "c-1000", "session-42", "minted-token", "sub-1000")
    manager = fakes.built[-1].kw["session_manager"]
    assert manager.config.actor_id == "sub-1000"
    assert "sub-1000" not in fakes.built[-1].kw["system_prompt"]
    assert manager.config.session_id == "session-42"
    assert manager.config.memory_id == "mem-test"
    assert list(manager.config.retrieval_config) == ["/users/{actorId}"]
    assert manager.region_name == "us-east-1"
    assert manager.closed is True


def test_the_model_id_and_region_come_from_the_environment(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token", "sub-1000")
    kw = fakes.built[-1].kw["model"].kw
    assert kw["model_id"] == "us.anthropic.claude-sonnet-4-5-20250929-v1:0" and kw["region_name"] == "us-east-1"
    # the model call has a stated read timeout and attempt count of its own
    assert kw["boto_client_config"].read_timeout == model.MODEL_READ_SECONDS
    assert kw["boto_client_config"].retries == {"total_max_attempts": 2}


def test_the_agent_is_cleaned_up_even_when_the_turn_fails(fakes, monkeypatch):
    def fail(self, prompt):
        raise RuntimeError("throttled")

    monkeypatch.setattr(FakeAgent, "__call__", fail)
    with pytest.raises(RuntimeError, match="throttled"):
        model.answer("my orders", "c-1000", "session-1", "minted-token", "sub-1000")
    assert fakes.built[-1].cleaned is True


def test_the_mcp_client_is_stopped_when_the_agent_fails_after_starting_it(fakes, monkeypatch):
    """Strands starts the MCP client during Agent construction. If the
    construction then fails, the client is stopped by its own closer."""
    clients = []

    class RecordingClient(FakeClient):
        def __init__(self, **kw):
            super().__init__(**kw)
            clients.append(self)

    def starts_then_fails(**kw):
        for t in kw["tools"]:
            if isinstance(t, FakeClient):
                t.started = True
        raise RuntimeError("model config invalid")

    monkeypatch.setattr(gateway, "make_client", RecordingClient)
    monkeypatch.setattr(model, "make_agent", starts_then_fails)
    with pytest.raises(RuntimeError, match="model config invalid"):
        model.answer("my orders", "c-1000", "session-1", "minted-token", "sub-1000")
    assert clients[-1].stopped == 1 and clients[-1].started is False


def test_the_mcp_client_is_stopped_once_on_the_happy_path_and_nothing_fails_to_close(fakes, capsys):
    model.answer("my orders", "c-1000", "session-1", "minted-token", "sub-1000")
    client = next(t for t in fakes.built[-1].kw["tools"] if isinstance(t, FakeClient))
    assert client.stopped == 1  # agent.cleanup stopped it; the extra stop was a no-op
    assert "cleanup failed" not in capsys.readouterr().out


def test_everything_created_is_closed_when_the_agent_cannot_be_built(fakes, monkeypatch):
    """The memory manager exists before the agent; if the agent (and with it
    the MCP connection) fails to build, the manager is still closed."""
    managers = []

    class RecordingManager(FakeManager):
        def __init__(self, config, region_name=None):
            super().__init__(config, region_name)
            managers.append(self)

    def explode(**kw):
        raise RuntimeError("gateway unreachable")

    monkeypatch.setattr(memory, "make_manager", RecordingManager)
    monkeypatch.setattr(model, "make_agent", explode)
    with pytest.raises(RuntimeError, match="gateway unreachable"):
        model.answer("my orders", "c-1000", "session-1", "minted-token", "sub-1000")
    assert managers and managers[-1].closed is True


def test_a_failing_close_does_not_stop_the_others_or_mask_the_answer(fakes, monkeypatch, capsys):
    monkeypatch.setattr(FakeManager, "close", lambda self: (_ for _ in ()).throw(RuntimeError("flush failed")))
    text, _, _ = _answer("my orders", "c-1000", "session-1", "minted-token", "sub-1000")
    assert text == "answered: my orders"
    assert fakes.built[-1].cleaned is True
    assert "cleanup failed" in capsys.readouterr().out


def test_the_trail_and_the_handoff_are_the_agents_hooks(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token", "sub-1000")
    hooks = fakes.built[-1].kw["hooks"]
    assert [type(h) for h in hooks] == [trail_module.Trail, handoff.Handoff]
    assert hooks[1].sandbox is not None


def test_the_model_is_told_to_read_the_file_not_retype_rows(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token", "sub-1000")
    prompt = fakes.built[-1].kw["system_prompt"]
    assert "orders.json" in prompt and "never retype order rows" in prompt
    assert "the agent writes that text into the sandbox as orders.json before your code runs" in prompt
    assert "call orders___list_orders again before computing" in prompt
    assert "if the file is missing when your code opens it" in prompt
    assert "if run_python says the file could not be written, run it again" in prompt
    assert "Every figure you calculate over the orders, a total, a count, an average, a difference, must be one run_python printed" in prompt
    assert "do not state a calculated number the code did not print" in prompt
    assert "Order numbers, dates and statuses you may read from the gateway's result as they are" in prompt


def _conversation_with_a_fetch(text):
    return [
        {"role": "user", "content": [{"text": "how much have I spent?"}]},
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t1", "name": "orders___list_orders", "input": {"customer_id": "c-1000"}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t1", "status": "success", "content": [{"text": text}]}}]},
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t2", "name": "run_python", "input": {"code": "print(1)"}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t2", "status": "success", "content": [{"text": "1"}]}}]},
        {"role": "assistant", "content": [{"text": "£743.80"}]},
    ]


def test_a_restored_conversations_latest_fetch_is_written_before_the_models_code_runs(fakes, monkeypatch):
    """The live run's second turn read orders.json before fetching and found
    nothing, because the sandbox session is new each turn. Trusted code now
    restores the last gateway result for it, and the sandbox writes the file
    just before the model's code first runs; a turn in which the model never
    runs code starts no session."""
    text = '{"customer_id": "c-1000", "orders": [{"order_id": 1033, "total": 12.0}]}'
    started, puts, executes = [], [], []
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: started.append(n) or "s5"))
    monkeypatch.setattr(sandbox.Sandbox, "put", staticmethod(lambda sid, path, t: puts.append((sid, path, t))))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: executes.append(len(puts)) or "1"))
    monkeypatch.setattr(FakeAgent, "restored_messages", _conversation_with_a_fetch(text))
    model.answer("thanks", "c-1000", "session-1", "minted-token", "sub-1000")
    assert started == [] and puts == []
    monkeypatch.setattr(FakeAgent, "runs_python", True)
    model.answer("which carrier?", "c-1000", "session-1", "minted-token", "sub-1000")
    assert started == ["analysis"]
    assert puts == [("s5", "orders.json", text)]
    assert executes == [1]  # the file was in place before the code ran


def test_restore_stages_the_file_and_starts_no_session():
    box = _Box()
    assert handoff.restore(_conversation_with_a_fetch("rows"), box) == ["orders.json"]
    assert box.staged == {"orders.json": "rows"} and box.unavailable == set()


def test_the_latest_outcome_wins_whether_it_succeeded_or_not():
    msgs = _conversation_with_a_fetch("first") + [
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t3", "name": "orders___list_orders", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t3", "status": "error", "content": [{"text": "denied"}]}}]},
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t4", "name": "orders___list_orders", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t4", "status": "success", "content": [{"text": "second"}]}}]},
    ]
    assert handoff.latest_results(msgs) == {"orders.json": "second"}
    assert handoff.latest_results(msgs[:-2]) == {"orders.json": None}  # the error was the latest
    assert handoff.latest_results([]) == {}  # never called: nothing to write, nothing to withhold
    assert handoff.latest_results(_conversation_with_a_fetch("")) == {"orders.json": None}


@pytest.mark.parametrize("latest", [
    {"status": "error", "content": [{"text": "Tool Execution Denied"}]},
    {"status": "success", "content": [{"text": "   "}]},
    {"status": "success", "content": [{"image": {}}]},
])
def test_a_failed_or_empty_latest_call_stays_withheld_on_the_next_turn(latest, monkeypatch):
    """The turn that saw the failure withheld the file; the next turn's
    fresh sandbox must rebuild that from the restored history, not restore
    the older success."""
    msgs = _conversation_with_a_fetch("old rows") + [
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t5", "name": "orders___list_orders", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": dict(latest, toolUseId="t5")}]},
    ]
    assert handoff.latest_results(msgs) == {"orders.json": None}
    puts = []
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: "s10"))
    monkeypatch.setattr(sandbox.Sandbox, "put", staticmethod(lambda sid, path, text: puts.append(path)))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: "ran"))
    box = sandbox.Sandbox()
    assert handoff.restore(msgs, box) == []
    assert puts == [] and box.unavailable == {"orders.json"}
    with pytest.raises(RuntimeError, match="orders.json not available this turn"):
        box.run_python(code="print(1)")
    later = msgs + [
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t6", "name": "orders___list_orders", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t6", "status": "success", "content": [{"text": "new rows"}]}}]},
    ]
    box2 = sandbox.Sandbox()
    assert handoff.restore(later, box2) == ["orders.json"]
    assert box2.unavailable == set() and box2.run_python(code="print(1)") == "ran"
    assert puts == ["orders.json"]  # the restored result was written before the code ran


def test_every_successful_handed_over_result_is_listed_for_the_check():
    msgs = _conversation_with_a_fetch("rows one") + [
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t5", "name": "orders___list_orders", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t5", "status": "error", "content": [{"text": "denied"}]}}]},
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t6", "name": "orders___list_orders", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t6", "status": "success", "content": [{"text": "rows two"}]}}]},
    ]
    assert handoff.handed_texts(msgs) == ["rows one", "rows two"]  # the failed call and run_python's "1" are not rows


def test_a_reused_tool_use_id_cannot_hand_another_tools_result_over():
    """An identifier a later run_python call happens to share with an old
    gateway call must not make that call's output the orders file."""
    msgs = _conversation_with_a_fetch("rows") + [
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t1", "name": "run_python", "input": {"code": "print(1)"}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t1", "status": "success", "content": [{"text": "python output"}]}}]},
    ]
    assert handoff.latest_results(msgs) == {"orders.json": "rows"}
    later = msgs + [
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t1", "name": "orders___list_orders", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t1", "status": "success", "content": [{"text": "newer rows"}]}}]},
    ]
    assert handoff.latest_results(later) == {"orders.json": "newer rows"}


def test_blocks_without_a_tool_use_id_are_never_matched():
    msgs = [
        {"role": "assistant", "content": [{"toolUse": {"name": "orders___list_orders", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"status": "success", "content": [{"text": "rows"}]}}]},
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "", "name": "orders___list_orders", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "", "status": "success", "content": [{"text": "rows"}]}}]},
        {"role": "user", "content": ["not a block", {"text": "plain"}]},
    ]
    assert handoff.latest_results(msgs) == {}


# --- the handoff: the gateway's result reaches the sandbox untouched ---------
class _Box:
    """A sandbox that records what trusted code staged or withheld."""

    def __init__(self):
        self.staged, self.unavailable = {}, set()

    def stage(self, path, text):
        self.staged[path] = text
        self.unavailable.discard(path)

    def withhold(self, path):
        self.staged.pop(path, None)
        self.unavailable.add(path)


def test_a_successful_gateway_result_is_staged_for_the_sandbox_exactly_as_returned(capsys):
    box = _Box()
    h = handoff.Handoff(box)
    text = '  {"customer_id": "c-1000", "orders": [{"order_id": 1033, "total": 12.0}]}\n'
    h.after(_Event({"name": "orders___list_orders", "input": {"customer_id": "c-1000"}, "toolUseId": "u1"},
                   {"status": "success", "content": [{"text": text}]}))
    assert box.staged == {"orders.json": text}  # whitespace and all
    assert h.staged == ["orders.json"]
    assert "1033" not in capsys.readouterr().out  # the log line carries the size, not the rows


def test_several_text_blocks_are_joined_and_other_content_dropped():
    box = _Box()
    handoff.Handoff(box).after(_Event({"name": "orders___list_orders", "input": {}, "toolUseId": "u1"},
                                      {"status": "success", "content": [{"text": "a"}, {"image": {}}, {"text": "b"}]}))
    assert box.staged == {"orders.json": "a\nb"}


@pytest.mark.parametrize("content", [None, "text", 7, [{"text": None}], [{"text": 3}, {"text": ""}]])
def test_a_malformed_result_reads_as_no_text_in_both_hooks(content):
    """A provider result whose content is not a list, or whose text is not a
    string, must not raise inside a hook and turn a reportable tool failure
    into a failed turn."""
    assert handoff._text_of({"status": "success", "content": content}) == ""
    assert trail_module._text_of({"status": "error", "content": content}) == ""
    box = _Box()
    handoff.Handoff(box).after(_Event({"name": "orders___list_orders", "input": {}, "toolUseId": "u1"},
                                      {"status": "success", "content": content}))
    assert box.staged == {} and box.unavailable == {"orders.json"}
    t = trail_module.Trail()
    use = {"name": "orders___list_orders", "input": {}, "toolUseId": "u1"}
    t.before(_Event(use))
    t.after(_Event(use, {"status": "error", "content": content}))
    assert t.steps[-1]["status"] == "error" and t.steps[-1]["error"] == ""


def test_a_write_that_fails_when_the_code_runs_is_reported_and_tried_again(monkeypatch):
    """The staged file is written just before the code runs. If that write
    fails the model sees the error and nothing ran; the file stays staged
    and the next call writes it again."""
    puts, attempts, executes = [], [], []

    def flaky_put(sid, path, text):
        attempts.append(text)
        if len(attempts) == 2:
            raise RuntimeError("write failed")
        puts.append((path, text))

    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: "s8"))
    monkeypatch.setattr(sandbox.Sandbox, "put", staticmethod(flaky_put))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: executes.append(code) or "ran"))
    box = sandbox.Sandbox()
    assert handoff.restore(_conversation_with_a_fetch("old rows"), box) == ["orders.json"]
    assert box.run_python(code="print(1)") == "ran" and puts == [("orders.json", "old rows")]
    h = handoff.Handoff(box)
    h.after(_Event({"name": "orders___list_orders", "input": {}, "toolUseId": "u9"},
                   {"status": "success", "content": [{"text": "new rows"}]}))
    with pytest.raises(RuntimeError, match="orders.json could not be written to the sandbox: write failed"):
        box.run_python(code="print(2)")
    assert executes == ["print(1)"]  # nothing ran over the old copy
    assert box.staged == {"orders.json": "new rows"} and box.unavailable == set()
    assert box.run_python(code="print(3)") == "ran"
    assert puts[-1] == ("orders.json", "new rows") and box.written == ["orders.json", "orders.json"]


def test_an_oversized_result_is_withheld_not_staged(monkeypatch):
    box = _Box()
    handoff.Handoff(box).after(_Event({"name": "orders___list_orders", "input": {}, "toolUseId": "u1"},
                                      {"status": "success", "content": [{"text": "x" * (handoff.MAX_HANDOFF_CHARS + 1)}]}))
    assert box.staged == {} and box.unavailable == {"orders.json"}
    msgs = _conversation_with_a_fetch("y" * (handoff.MAX_HANDOFF_CHARS + 1))
    assert handoff.latest_results(msgs) == {"orders.json": None}


def test_a_failed_gateway_call_or_an_empty_result_also_withholds_the_old_file(monkeypatch):
    """After restore() put last turn's file in place, a failed call or a
    result with nothing in it must not leave that file readable as current."""
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: "s9"))
    monkeypatch.setattr(sandbox.Sandbox, "put", staticmethod(lambda sid, path, text: None))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: "ran"))
    for result in (
        {"status": "error", "content": [{"text": "Tool Execution Denied"}]},
        {"status": "success", "content": [{"text": "   "}]},
        {"status": "success", "content": [{"image": {}}]},
    ):
        box = sandbox.Sandbox()
        handoff.restore(_conversation_with_a_fetch("old rows"), box)
        assert box.run_python(code="print(1)") == "ran"
        handoff.Handoff(box).after(_Event({"name": "orders___list_orders", "input": {}, "toolUseId": "u1"}, result))
        with pytest.raises(RuntimeError, match="orders.json not available this turn"):
            box.run_python(code="print(1)")


def test_the_tool_description_tells_the_model_to_read_the_file_not_embed_rows():
    description = " ".join(sandbox.Sandbox().run_python.tool_spec["description"].split())
    assert "orders.json" in description
    assert "Never put order rows into the code" in description
    assert "the agent writes that text into the sandbox as orders.json" in description
    assert "refuses to run until orders___list_orders is called again" in description
    assert "Print every figure your answer will calculate, a total, a count, an average, a difference" in description
    assert "do not state a calculated number the code did not print" in description
    assert "list of dicts" not in description and "into the code itself" not in description


def test_other_tools_and_failed_calls_are_not_handed_over():
    box = _Box()
    h = handoff.Handoff(box)
    h.after(_Event({"name": "run_python", "input": {"code": "print(1)"}, "toolUseId": "u1"},
                   {"status": "success", "content": [{"text": "1"}]}))
    assert box.unavailable == set()  # an unrelated tool changes nothing
    h.after(_Event({"name": "orders___list_orders", "input": {"customer_id": "c-1001"}, "toolUseId": "u2"},
                   {"status": "error", "content": [{"text": "Tool Execution Denied"}]}))
    assert box.staged == {} and h.staged == []
    assert box.unavailable == {"orders.json"}  # a failed call withholds any older copy


def test_a_staged_file_is_written_once_before_the_first_run_and_not_again(monkeypatch):
    started, puts, executes = [], [], []
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: started.append(n) or "s3"))
    monkeypatch.setattr(sandbox.Sandbox, "put", staticmethod(lambda sid, path, text: puts.append((sid, path, text))))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: executes.append(len(puts)) or "ok"))
    box = sandbox.Sandbox()
    box.stage("orders.json", "{}")
    box.stage("orders.json", "{}")
    assert started == [] and puts == []
    box.run_python(code="print(1)")
    box.run_python(code="print(2)")
    assert started == ["analysis"] and puts == [("s3", "orders.json", "{}")] and executes == [1, 1]


def test_concurrent_calls_share_one_session_and_run_one_at_a_time(monkeypatch):
    """Two run_python calls arriving together must not each start a session
    and leak one; the lock makes the second wait for the first."""
    import threading
    import time

    started, running, overlap = [], [], []

    def slow_start(i, n):
        time.sleep(0.05)
        started.append(n)
        return f"s{len(started)}"

    def execute(sid, code):
        running.append(sid)
        overlap.append(len(running))
        time.sleep(0.05)
        running.remove(sid)
        return "ok"

    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(slow_start))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(execute))
    box = sandbox.Sandbox()
    threads = [threading.Thread(target=box.run_python, kwargs={"code": "print(1)"}) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert started == ["analysis"] and max(overlap) == 1


# --- the trail records the model's choices in order --------------------------
class _Event:
    def __init__(self, tool_use, result=None):
        self.tool_use = tool_use
        self.result = result


def test_the_trail_records_each_call_with_its_arguments_and_outcome():
    t = trail_module.Trail()
    use = {"name": "orders___list_orders", "input": {"customer_id": "c-1001"}, "toolUseId": "u1"}
    t.before(_Event(use))
    t.after(_Event(use, {"status": "error", "content": [{"text": "Tool Execution Denied: policy"}]}))
    use2 = {"name": "run_python", "input": {"code": "print(1)"}, "toolUseId": "u2"}
    t.before(_Event(use2))
    t.after(_Event(use2, {"status": "success", "content": [{"text": "1"}]}))
    use3 = {"name": "orders___list_orders", "input": {"customer_id": "c-1000"}, "toolUseId": "u3"}
    t.before(_Event(use3))
    t.after(_Event(use3, {"status": "success", "content": [{"text": '{"orders": [{"order_id": 1033}]}'}]}))
    assert t.steps == [
        {"tool": "orders___list_orders", "input": {"customer_id": "c-1001"}, "status": "error",
         "error": "Tool Execution Denied: policy"},
        {"tool": "run_python", "input": {"code": "print(1)"}, "status": "success", "output": "1"},
        {"tool": "orders___list_orders", "input": {"customer_id": "c-1000"}, "status": "success"},  # rows are not carried
    ]
    assert json.dumps(t.steps)  # what the handler returns must serialise


def test_what_the_code_printed_is_carried_in_the_trail_up_to_the_preview_and_whole_as_evidence():
    t = trail_module.Trail()
    use = {"name": "run_python", "input": {"code": "print('x' * 5000)"}, "toolUseId": "u1"}
    t.before(_Event(use))
    t.after(_Event(use, {"status": "success", "content": [{"text": "x" * 5000 + " count 7"}]}))
    assert len(t.steps[0]["output"]) == trail_module.OUTPUT_PREVIEW
    assert t.evidence == ["x" * 5000 + " count 7"]  # the check after the answer sees the whole of it
    use2 = {"name": "run_python", "input": {"code": "nope"}, "toolUseId": "u2"}
    t.before(_Event(use2))
    t.after(_Event(use2, {"status": "error", "content": [{"text": "NameError 404"}]}))
    assert t.evidence == ["x" * 5000 + " count 7"]  # a failed call is no evidence


def test_figures_in_the_answer_are_checked_against_what_the_code_printed_and_the_rows_hold():
    """What run_python printed this turn, whole, supports any figure; a
    successful result of the order tool supports only what is read from a
    row, an identifier, a year or an amount; the prompt and the date support
    years. Nothing else does: not an earlier turn's code output, not a
    failed result, not another tool. A count or a difference the model
    worked out in its head is left standing, and so, the check being
    lexical, is a day of the month read from a row."""
    evidence = ["Total orders: 9\nRoyal Mail orders: 3\n" + "x" * 2500 + "\nTotal: £743.80\nLate count: 42"]
    def result(tid, name, text, status="success"):
        return [
            {"role": "assistant", "content": [{"toolUse": {"toolUseId": tid, "name": name, "input": {}}}]},
            {"role": "user", "content": [{"toolResult": {"toolUseId": tid, "status": status, "content": [{"text": text}]}}]},
        ]
    messages = (
        result("t1", "orders___list_orders", '{"orders": [{"order_id": 1033, "placed_at": "2026-06-18", "total": 6.80, "items": 6}]}')
        + result("t2", "run_python", "Earlier count: 100\nEarlier amount: 5.50")   # an earlier turn's code output
        + result("t3", "orders___list_orders", '{"total": 250.00}', status="error")  # a failed result
        + result("t4", "some_other_tool", "value 777 and 8.25")                     # another tool
        + [{"role": "assistant", "content": [{"text": "There were 12 of them."}]}]  # the model's own words
    )
    answer = ("Looking at your 9 orders, 3 went with Royal Mail and the other 6 with DPD, £743.80 in all, 42 late; "
              "order 1033 on 18 June 2026 cost £6.80; 12 before, 100 earlier at 5.50, 250.00 failed, 777 at 8.25, "
              "and 743.8 is not how the code wrote it.")
    assert model.unsupported_figures(answer, evidence, messages, "2026-10-07") == [
        "100", "12", "250.00", "5.50", "6", "743.8", "777", "8.25",
    ]  # "18 June" is a day beside a month, not a figure
    # identifiers, ordinal days and days beside month names are not figures to check
    assert model.figures_claimed("I act for c-1000, not c-1001; order 1255 came on 20th July, 7 October was quiet, October 7 too.") == {"1255"}
    assert model.unsupported_figures("I can only help customer c-1000, not c-1001.", [], [], "2026-10-07") == []
    # the prompt supports nothing: a figure the customer wrote is not evidence of itself
    assert model.unsupported_figures("Is it £999? Yes, £999, in 2025.", [], [], "2026-10-07") == ["2025", "999"]
    assert model.unsupported_figures("Order c-1000 has 1234 items for £9999.", [], [], "2026-10-07") == ["1234", "9999"]  # c-1000 is an identifier
    assert model.unsupported_figures("No figures here.", evidence, messages, "2026-10-07") == []
    assert model.unsupported_figures("", [], [], "2026-10-07") == []


def test_a_named_figure_gets_one_restatement(fakes, monkeypatch):
    """When the check names a figure in the first answer, trusted code asks
    the model once to restate from what the tools returned; the response
    says it did and carries what the check names after that."""
    rows = [
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t1", "name": "orders___list_orders", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t1", "status": "success", "content": [{"text": '{"order_id": 1255, "total": 9.00}'}]}}]},
    ]
    monkeypatch.setattr(FakeAgent, "restored_messages", rows)
    monkeypatch.setattr(model, "today", lambda: "2026-10-07")
    prompts = []
    answers = iter(["9 orders, 6 of them DPD, placed since 2025.", "Order 1255 cost £9.00, placed in 2026."])

    def scripted(self, prompt):
        prompts.append(prompt)
        return FakeResult(next(answers))

    monkeypatch.setattr(FakeAgent, "__call__", scripted)
    turn = model.answer("how many since 2025?", "c-1000", "session-1", "minted-token", "sub-1000")
    assert turn["restated"] is True and turn["unsupported_figures"] == []
    assert turn["result"] == "Order 1255 cost £9.00, placed in 2026."
    assert prompts[0] == "how many since 2025?"
    assert "2025, 6, 9" in prompts[1] and "Restate your answer" in prompts[1]  # the named figures, once


def test_what_the_restatement_still_names_is_returned_and_there_is_no_second(fakes, monkeypatch):
    calls = []
    monkeypatch.setattr(FakeAgent, "__call__", lambda self, prompt: calls.append(prompt) or FakeResult("The other 6 went with DPD."))
    turn = model.answer("how many?", "c-1000", "session-1", "minted-token", "sub-1000")
    assert turn["restated"] is True and turn["unsupported_figures"] == ["6"]
    assert len(calls) == 2


def test_the_date_is_read_once_for_the_prompt_and_the_check(fakes, monkeypatch):
    """A turn crossing midnight tells the model one date and checks against
    the same one."""
    clock = iter(["2026-12-31", "2027-01-01", "2027-01-01"])
    monkeypatch.setattr(model, "today", lambda: next(clock))
    monkeypatch.setattr(FakeAgent, "__call__", lambda self, prompt: FakeResult("You spent nothing in 2026."))
    turn = model.answer("this year?", "c-1000", "session-1", "minted-token", "sub-1000")
    assert "Today is 2026-12-31" in fakes.built[-1].kw["system_prompt"]
    assert turn["unsupported_figures"] == [] and turn["restated"] is False  # 2026 is the year the model was told


def test_the_restate_message_and_the_figures_it_names_are_bounded(fakes, monkeypatch):
    """A model that writes a great many figures, or a very long run of
    digits, cannot make the restate message long: only the first few are
    named and a run past MAX_FIGURE_CHARS is not a figure at all."""
    prompts = []
    flood = " ".join(str(n) for n in range(100, 150)) + " and " + "9" * 500
    monkeypatch.setattr(FakeAgent, "__call__", lambda self, prompt: prompts.append(prompt) or FakeResult(flood))
    turn = model.answer("how many?", "c-1000", "session-1", "minted-token", "sub-1000")
    assert len(turn["unsupported_figures"]) == 50 and "9" * 500 not in turn["unsupported_figures"]
    assert "100, 101, 102, 103, 104, 105, 106, 107, 108, 109 and 40 more" in prompts[1]
    assert len(prompts[1]) < len(model.RESTATE) + 200


def test_the_sandbox_is_closed_first_then_the_rest_in_reverse(fakes, monkeypatch):
    order = []
    monkeypatch.setattr(sandbox.Sandbox, "close", lambda self: order.append("sandbox"))
    monkeypatch.setattr(FakeManager, "close", lambda self: order.append("memory"))
    monkeypatch.setattr(FakeAgent, "cleanup", lambda self: order.append("agent"))
    model.answer("hi", "c-1000", "session-1", "minted-token", "sub-1000")
    assert order[0] == "sandbox" and order[-1] == "memory" and "agent" in order


def test_a_clean_answer_is_not_restated(fakes, monkeypatch):
    calls = []
    monkeypatch.setattr(FakeAgent, "__call__", lambda self, prompt: calls.append(prompt) or FakeResult("Nothing to report."))
    turn = model.answer("anything new?", "c-1000", "session-1", "minted-token", "sub-1000")
    assert turn["restated"] is False and turn["unsupported_figures"] == [] and len(calls) == 1


def test_the_runtime_log_never_carries_the_tool_input(capsys):
    """The trail goes back to the customer; CloudWatch gets names and sizes."""
    t = trail_module.Trail()
    code = "orders = [{'order_id': 1033, 'total': 12.0}]\nprint(sum(o['total'] for o in orders))"
    use = {"name": "run_python", "input": {"code": code}, "toolUseId": "u1"}
    t.before(_Event(use))
    t.after(_Event(use, {"status": "success", "content": [{"text": "12.0"}]}))
    out = capsys.readouterr().out
    assert "1033" not in out and "12.0" not in out and "orders" not in out
    assert f"model chose run_python (input {len(code)} chars)" in out
    assert t.steps[0]["input"]["code"] == code


def test_the_trail_cancels_the_call_past_the_budget_then_ends_the_turn():
    """Cancelling alone would let the model ask forever; the second ask after
    the budget raises and the turn ends."""
    t = trail_module.Trail(max_tool_calls=2)
    events = []
    for i in range(3):
        e = _Event({"name": "run_python", "input": {"code": "print(1)"}, "toolUseId": f"u{i}"})
        e.cancel_tool = None
        t.before(e)
        events.append(e)
    assert [e.cancel_tool for e in events[:2]] == [None, None]
    assert "budget" in events[2].cancel_tool
    assert t.executed == 2
    assert [s.get("status") for s in t.steps] == [None, None, "cancelled"]
    fourth = _Event({"name": "run_python", "input": {"code": "print(2)"}, "toolUseId": "u3"})
    fourth.cancel_tool = None
    with pytest.raises(trail_module.BudgetExceeded):
        t.before(fourth)
    assert [s.get("status") for s in t.steps][-2:] == ["cancelled", "cancelled"]


def test_a_budget_overrun_still_closes_everything(fakes, monkeypatch):
    def keeps_asking(self, prompt):
        raise trail_module.BudgetExceeded("kept asking")

    monkeypatch.setattr(FakeAgent, "__call__", keeps_asking)
    with pytest.raises(trail_module.BudgetExceeded):
        model.answer("loop forever", "c-1000", "session-1", "minted-token", "sub-1000")
    assert fakes.built[-1].cleaned is True


def test_the_trail_ignores_a_result_it_never_saw_start():
    t = trail_module.Trail()
    t.after(_Event({"name": "x", "toolUseId": "nope"}, {"status": "success", "content": []}))
    assert t.steps == []


# --- the sandbox tool: one session, started on first use, stopped once --------
class FakeInterpreter:
    """Records invoke calls and replays a canned stream for each."""

    def __init__(self, streams):
        self.streams = list(streams)
        self.invocations = []

    def invoke_code_interpreter(self, **kwargs):
        self.invocations.append(kwargs)
        return {"stream": self.streams.pop(0)}


def _text_event(text, is_error=False):
    return {"result": {"isError": is_error, "content": [{"type": "text", "text": text}]}}


@pytest.fixture
def fake(monkeypatch):
    fake = FakeInterpreter([])
    monkeypatch.setattr(sandbox, "client", lambda: fake)
    return fake


def test_a_tool_error_raises_so_the_model_sees_the_traceback(fake):
    fake.streams = [[_text_event("NameError: pandas", is_error=True)]]
    with pytest.raises(RuntimeError, match="NameError"):
        sandbox.execute_code("s1", "pandas.nope()")


def test_run_python_starts_one_session_and_reuses_it(fake, monkeypatch):
    started, stopped = [], []
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda interpreter, name: started.append((interpreter, name)) or "s9"))
    monkeypatch.setattr(sandbox.Sandbox, "stop", staticmethod(lambda interpreter, sid: stopped.append(sid)))
    fake.streams = [[_text_event("7")], [_text_event("14")]]
    box = sandbox.Sandbox()
    assert box.run_python(code="print(7)") == "7"
    assert box.run_python(code="print(14)") == "14"
    assert started == [("ci-test", "analysis")]
    assert {i["sessionId"] for i in fake.invocations} == {"s9"}
    assert [i["name"] for i in fake.invocations] == ["executeCode", "executeCode"]
    box.close()
    box.close()
    assert stopped == ["s9"]


def test_a_stream_without_a_result_is_an_error_not_an_empty_answer(fake):
    fake.streams = [[{"accessDeniedException": {"message": "not allowed"}}]]
    with pytest.raises(RuntimeError, match="accessDeniedException.*not allowed"):
        sandbox.execute_code("s1", "print(1)")


def test_long_output_is_truncated_for_the_model(fake):
    fake.streams = [[_text_event("x" * (sandbox.MAX_OUTPUT_CHARS + 500))]]
    out = sandbox.execute_code("s1", "print('x' * 9000)")
    assert len(out) < sandbox.MAX_OUTPUT_CHARS + 100
    assert "truncated" in out


def test_a_huge_error_is_bounded_too(fake):
    fake.streams = [[_text_event("Traceback" + "e" * 30000, is_error=True)]]
    with pytest.raises(RuntimeError) as exc:
        sandbox.execute_code("s1", "raise")
    assert len(str(exc.value)) <= sandbox.MAX_OUTPUT_CHARS + 80
    assert str(exc.value).startswith("Traceback") and "truncated" in str(exc.value)


def test_separators_count_towards_the_bound(fake):
    fake.streams = [[_text_event("a" * 4000), _text_event("b" * 4000), _text_event("c")]]
    out = sandbox.execute_code("s1", "print()")
    body = out.split("\n... output truncated")[0]
    assert len(body) <= sandbox.MAX_OUTPUT_CHARS
    assert "truncated" in out


def test_output_past_the_limit_is_drained_not_retained(fake):
    """Many chunks beyond the limit are read and dropped; what is kept never
    exceeds the limit, whatever the service sends."""
    fake.streams = [[_text_event("y" * 1000) for _ in range(50)]]
    out = sandbox.execute_code("s1", "print('y' * 50000)")
    assert sandbox.MAX_OUTPUT_CHARS - 50 <= out.count("y") <= sandbox.MAX_OUTPUT_CHARS
    assert "truncated" in out


def test_oversized_code_is_refused_before_a_session_is_started(monkeypatch):
    started = []
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: started.append(n) or "s1"))
    with pytest.raises(ValueError, match="limit"):
        sandbox.Sandbox().run_python(code="x" * (sandbox.MAX_CODE_CHARS + 1))
    assert started == []


def test_a_failed_stop_is_retried_once_then_raised_with_the_session_id_kept(monkeypatch):
    attempts = []

    def flaky_stop(interpreter, sid):
        attempts.append(sid)
        if len(attempts) < 3:
            raise RuntimeError("throttled")

    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: "s7"))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: "ok"))
    monkeypatch.setattr(sandbox.Sandbox, "stop", staticmethod(flaky_stop))
    box = sandbox.Sandbox()
    box.run_python(code="print(1)")
    with pytest.raises(RuntimeError):
        box.close()  # two attempts, both fail
    assert box.session_id == "s7" and attempts == ["s7", "s7"]
    box.close()  # third attempt succeeds
    assert box.session_id is None and attempts == ["s7", "s7", "s7"]


def test_the_sandbox_client_makes_one_http_attempt(monkeypatch):
    made = {}

    class FakeBoto:
        @staticmethod
        def client(name, config=None):
            made["name"], made["config"] = name, config
            return object()

    monkeypatch.setattr(sandbox, "_client", None)
    monkeypatch.setattr(sandbox, "boto3", FakeBoto)
    sandbox.client()
    assert made["name"] == "bedrock-agentcore"
    assert made["config"].read_timeout == sandbox.WAIT_SECONDS
    assert made["config"].retries == {"total_max_attempts": 1}
    monkeypatch.setattr(sandbox, "_client", None)


def test_a_call_that_outlives_the_deadline_is_abandoned_with_an_error(monkeypatch):
    """Wall clock, not a socket timeout: a call that keeps the agent waiting
    past WAIT_SECONDS is given up and reported, whatever the service does."""
    import threading
    import time

    release = threading.Event()

    class Slow:
        def invoke_code_interpreter(self, **kw):
            release.wait(5)
            return {"stream": [_text_event("late")]}

    monkeypatch.setattr(sandbox, "client", lambda: Slow())
    monkeypatch.setattr(sandbox, "WAIT_SECONDS", 0.2)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="did not finish within"):
        sandbox.execute_code("s1", "while True: pass")
    assert time.monotonic() - started < 2
    release.set()


def test_a_call_within_the_deadline_returns_its_output(fake):
    fake.streams = [[_text_event("fast")]]
    assert sandbox.execute_code("s1", "print('fast')") == "fast"


def test_starting_and_stopping_a_session_have_the_same_deadline_and_bound(monkeypatch):
    """Every call to the service goes through the deadline and the admission
    bound, not only write and execute; a stop waits for a slot instead of
    being refused, so a busy process still ends its sessions."""
    import threading
    import time

    class Slow:
        def start_code_interpreter_session(self, **kw):
            time.sleep(1)
            return {"sessionId": "late"}

        def stop_code_interpreter_session(self, **kw):
            return {}

    monkeypatch.setattr(sandbox, "client", lambda: Slow())
    monkeypatch.setattr(sandbox, "WAIT_SECONDS", 0.2)
    with pytest.raises(sandbox.Abandoned, match="startCodeInterpreterSession did not finish within"):
        sandbox.session_for("ci-test", "analysis")
    time.sleep(1)  # the abandoned start gives its slot back when its call ends
    monkeypatch.setattr(sandbox, "_slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(sandbox, "MAX_IN_FLIGHT", 1)
    assert sandbox._slots.acquire(blocking=False)
    with pytest.raises(RuntimeError, match="startCodeInterpreterSession refused"):
        sandbox.session_for("ci-test", "analysis")
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="stopCodeInterpreterSession refused"):
        sandbox.stop_session("ci-test", "s1")
    assert time.monotonic() - started >= 0.2  # the stop waited for a slot before giving up
    sandbox._slots.release()
    assert sandbox.stop_session("ci-test", "s1") is None


def test_one_deadline_spans_the_wait_for_a_slot_and_the_call(monkeypatch):
    """A stop that waited for a slot does not then get a whole deadline for
    the call as well: six minutes of cleanup is not three."""
    import threading
    import time

    monkeypatch.setattr(sandbox, "_slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(sandbox, "MAX_IN_FLIGHT", 1)
    monkeypatch.setattr(sandbox, "WAIT_SECONDS", 0.3)
    assert sandbox._slots.acquire(blocking=False)
    threading.Timer(0.15, sandbox._slots.release).start()  # a slot comes free half way through

    class SlowStop:
        def stop_code_interpreter_session(self, **kw):
            time.sleep(0.5)
            return {}

    monkeypatch.setattr(sandbox, "client", lambda: SlowStop())
    started = time.monotonic()
    with pytest.raises(sandbox.Abandoned, match="stopCodeInterpreterSession did not finish"):
        sandbox.stop_session("ci-test", "s1")
    elapsed = time.monotonic() - started
    assert 0.25 <= elapsed < 0.45  # one deadline from the ask, not one per phase
    time.sleep(0.5)


def test_a_start_the_agent_gave_up_on_is_stopped_when_it_comes_back(monkeypatch, capsys):
    """Nothing tracks a session created after its start was abandoned, so
    the worker that sees it come back stops it at once."""
    import time

    stopped = []

    class LateStart:
        def start_code_interpreter_session(self, **kw):
            time.sleep(0.3)
            return {"sessionId": "late-session"}

        def stop_code_interpreter_session(self, **kw):
            stopped.append(kw["sessionId"])
            return {}

    monkeypatch.setattr(sandbox, "client", lambda: LateStart())
    monkeypatch.setattr(sandbox, "WAIT_SECONDS", 0.1)
    with pytest.raises(sandbox.Abandoned):
        sandbox.session_for("ci-test", "analysis")
    time.sleep(0.5)
    assert stopped == ["late-session"]
    assert "stopped sandbox session late-session, created after its start was abandoned" in capsys.readouterr().out


def test_after_an_abandoned_call_the_sandbox_runs_nothing_more_this_turn(monkeypatch):
    """The call given up on may still be running in the session, so a second
    run_python is refused rather than started beside it; the stop at the
    end of the turn is what ends the session."""
    executes = []
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: "s15"))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: executes.append(code) or (_ for _ in ()).throw(sandbox.Abandoned("executeCode did not finish"))))
    monkeypatch.setattr(sandbox.Sandbox, "stop", staticmethod(lambda i, sid: None))
    box = sandbox.Sandbox()
    with pytest.raises(sandbox.Abandoned):
        box.run_python(code="while True: pass")
    with pytest.raises(RuntimeError, match="gave up waiting on an earlier call this turn and will not run again"):
        box.run_python(code="print(1)")
    assert executes == ["while True: pass"]
    box.close()


def test_a_late_stop_goes_through_the_same_bound_as_every_call(monkeypatch, capsys):
    """A session created after its start was abandoned is stopped through
    stop_session, the bounded call, on the late worker, never through the
    client directly; with every slot taken for the whole deadline it is
    refused and logged like any other call."""
    import threading
    import time
    from concurrent.futures import Future

    bounded, direct = [], []
    monkeypatch.setattr(sandbox, "stop_session", lambda interpreter, sid: bounded.append((interpreter, sid)))
    monkeypatch.setattr(sandbox, "_stop", lambda interpreter, sid: direct.append(sid))
    done = Future()
    done.set_result("late-session")
    sandbox._stop_late("ci-test", done)
    time.sleep(0.2)
    assert bounded == [("ci-test", "late-session")] and direct == []
    assert "stopped sandbox session late-session, created after its start was abandoned" in capsys.readouterr().out

    monkeypatch.undo()
    monkeypatch.setattr(sandbox, "WAIT_SECONDS", 0.1)
    monkeypatch.setattr(sandbox, "MAX_IN_FLIGHT", 1)
    monkeypatch.setattr(sandbox, "_slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(sandbox, "_stop", lambda interpreter, sid: direct.append(sid))
    assert sandbox._slots.acquire(blocking=False)  # every slot is taken for the whole deadline
    sandbox._stop_late("ci-test", done)
    time.sleep(0.4)
    sandbox._slots.release()
    assert direct == []
    assert "stopping late sandbox session late-session failed: RuntimeError" in capsys.readouterr().out


def test_late_stops_waiting_for_their_worker_are_bounded(monkeypatch, capsys):
    import threading
    from concurrent.futures import Future

    monkeypatch.setattr(sandbox, "_late_pending", threading.BoundedSemaphore(1))
    monkeypatch.setattr(sandbox, "MAX_LATE_PENDING", 1)
    assert sandbox._late_pending.acquire(blocking=False)  # one is pending already
    done = Future()
    done.set_result("late-2")
    sandbox._stop_late("ci-test", done)
    sandbox._late_pending.release()
    assert "late stop of sandbox session late-2 dropped, 1 already pending; its lifetime ends it" in capsys.readouterr().out


def test_a_stream_is_read_to_its_end_before_a_failure_is_raised(fake):
    seen = []

    def events():
        for e in [{"throttlingException": {"message": "slow down"}}, _text_event("after")]:
            seen.append(sorted(e))
            yield e

    fake.streams = [events()]
    with pytest.raises(RuntimeError, match="throttlingException"):
        sandbox.execute_code("s1", "print(1)")
    assert seen == [["throttlingException"], ["result"]]


def test_an_abandoned_write_marks_the_sandbox_too(monkeypatch):
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: "s14"))
    monkeypatch.setattr(sandbox.Sandbox, "put", staticmethod(lambda sid, path, text: (_ for _ in ()).throw(sandbox.Abandoned("writeFiles did not finish"))))
    box = sandbox.Sandbox()
    box.stage("orders.json", "{}")
    with pytest.raises(sandbox.Abandoned):
        box.run_python(code="print(1)")
    assert box.abandoned is True and box.staged == {"orders.json": "{}"}


def test_a_session_with_an_abandoned_call_is_stopped_and_says_so(monkeypatch, capsys):
    stopped = []
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: "s12"))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: (_ for _ in ()).throw(sandbox.Abandoned("executeCode did not finish"))))
    monkeypatch.setattr(sandbox.Sandbox, "stop", staticmethod(lambda i, sid: stopped.append(sid)))
    box = sandbox.Sandbox()
    with pytest.raises(sandbox.Abandoned):
        box.run_python(code="while True: pass")
    assert box.abandoned is True
    box.close()
    assert stopped == ["s12"] and box.session_id is None
    assert "stopping sandbox session s12 with an abandoned call still in flight" in capsys.readouterr().out


def test_a_call_past_the_in_flight_limit_is_refused_and_a_finished_call_frees_its_slot(fake, monkeypatch):
    """Nothing queues behind the workers: with every slot taken the call is
    refused outright, and a slot comes back when its call finishes, however
    it ended."""
    import threading

    monkeypatch.setattr(sandbox, "_slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(sandbox, "MAX_IN_FLIGHT", 1)
    assert sandbox._slots.acquire(blocking=False)  # someone else's call is in flight
    with pytest.raises(RuntimeError, match="executeCode refused: the sandbox already has 1 calls in flight"):
        sandbox.execute_code("s1", "print(1)")
    sandbox._slots.release()
    fake.streams = [[_text_event("one")], [_text_event("NameError", is_error=True)], [_text_event("three")]]
    assert sandbox.execute_code("s1", "print(1)") == "one"
    with pytest.raises(RuntimeError, match="NameError"):
        sandbox.execute_code("s1", "nope")
    assert sandbox.execute_code("s1", "print(3)") == "three"  # both earlier calls gave their slot back


def test_closing_an_unused_sandbox_stops_nothing(monkeypatch):
    stopped = []
    monkeypatch.setattr(sandbox.Sandbox, "stop", staticmethod(lambda interpreter, sid: stopped.append(sid)))
    sandbox.Sandbox().close()
    assert stopped == []


def test_a_failure_is_described_by_class_and_aws_code_never_by_message():
    from botocore.exceptions import ClientError

    secret = 'Bearer eyJhbGciOi.eyJzdWIi.sig {"order_id": 1033} print(total)'
    assert trail_module.describe(RuntimeError(secret)) == "RuntimeError"
    denied = ClientError({"Error": {"Code": "AccessDeniedException", "Message": secret}}, "InvokeCodeInterpreter")
    assert trail_module.describe(denied) == "ClientError AccessDeniedException"
    # botocore names a modelled error's class after its code; it is said once
    modelled = type("ValidationException", (ClientError,), {})
    assert trail_module.describe(modelled({"Error": {"Code": "ValidationException", "Message": secret}}, "GetToken")) == "ValidationException"


def test_a_failing_closes_message_stays_out_of_the_log(fakes, monkeypatch, capsys):
    def leaky_stop(interpreter, sid):
        raise RuntimeError('Bearer eyJhbGciOi.eyJzdWIi.sig {"order_id": 1033}')

    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: "s13"))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: "1"))
    monkeypatch.setattr(sandbox.Sandbox, "stop", staticmethod(leaky_stop))
    monkeypatch.setattr(FakeAgent, "runs_python", True)
    model.answer("hi", "c-1000", "session-1", "minted-token", "sub-1000")
    out = capsys.readouterr().out
    assert "cleanup failed in Sandbox.close: RuntimeError" in out
    assert "eyJ" not in out and "1033" not in out


# --- the real Strands loop, with a scripted model ----------------------------
from strands.models import Model as _StrandsModel  # noqa: E402


class ScriptedModel(_StrandsModel):
    """A Strands model that asks for the tools in its script, then answers.
    The agent, the executor, the hooks and the tools are the real ones. It
    subclasses the Strands base so that whatever the pinned or a newer
    Agent reads off a model, such as `stateful`, is there."""

    def __init__(self, script):
        self.script, self.calls = list(script), 0

    def update_config(self, **kw):
        pass

    def get_config(self):
        return {}

    async def structured_output(self, *a, **kw):
        raise NotImplementedError
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kw):
        self.calls += 1
        step = self.script.pop(0) if self.script else ("text", "done")
        yield {"messageStart": {"role": "assistant"}}
        if step[0] == "tool":
            yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"t{self.calls}", "name": step[1]}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(step[2])}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockDelta": {"delta": {"text": step[1]}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}, "metrics": {"latencyMs": 1}}}


def _real_agent(script, box, trail):
    from strands import Agent
    from strands.agent.conversation_manager import SlidingWindowConversationManager
    from strands.tools.executors import SequentialToolExecutor

    return Agent(
        model=ScriptedModel(script),
        tools=[orders___list_orders, box.run_python],
        hooks=[trail, handoff.Handoff(box)],
        conversation_manager=SlidingWindowConversationManager(window_size=40, should_truncate_results=False),
        tool_executor=SequentialToolExecutor(),
        callback_handler=None,
    )


from strands import tool as _strands_tool


@_strands_tool
def orders___list_orders(customer_id: str) -> str:
    """Stands in for the gateway's tool.

    Args:
        customer_id: the customer.
    """
    return json.dumps({"customer_id": customer_id, "orders": [{"order_id": 1033, "total": 12.0}]})


def test_in_the_real_loop_the_gateway_result_is_in_the_sandbox_before_the_models_code_runs(monkeypatch):
    started, puts, executes, stopped = [], [], [], []
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: started.append(n) or "s20"))
    monkeypatch.setattr(sandbox.Sandbox, "put", staticmethod(lambda sid, path, text: puts.append((sid, path, text))))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: executes.append((len(puts), code)) or "12.00"))
    monkeypatch.setattr(sandbox.Sandbox, "stop", staticmethod(lambda i, sid: stopped.append(sid)))
    box, t = sandbox.Sandbox(), trail_module.Trail()
    agent = _real_agent([
        ("tool", "orders___list_orders", {"customer_id": "c-1000"}),
        ("tool", "run_python", {"code": "print(1)"}),
        ("text", "You have spent £12.00."),
    ], box, t)
    result = agent("how much?")
    assert str(result).strip() == "You have spent £12.00."
    assert started == ["analysis"]
    assert puts == [("s20", "orders.json", orders___list_orders(customer_id="c-1000"))]
    assert executes == [(1, "print(1)")]  # the file was written before the code ran
    assert [(s["tool"], s["status"]) for s in t.steps] == [("orders___list_orders", "success"), ("run_python", "success")]
    box.close()
    assert stopped == ["s20"]


def test_in_the_real_loop_a_failed_execution_reaches_the_model_as_a_tool_error(monkeypatch):
    """What the post says lets the model fix its code and run again: the
    sandbox's error is placed in the next request to the model as the tool
    result, with its text."""
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: "s22"))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: (_ for _ in ()).throw(RuntimeError("NameError: name 'pandas' is not defined"))))
    monkeypatch.setattr(sandbox.Sandbox, "stop", staticmethod(lambda i, sid: None))
    box, t = sandbox.Sandbox(), trail_module.Trail()
    agent = _real_agent([("tool", "run_python", {"code": "pandas.nope()"}), ("text", "I will fix that.")], box, t)
    seen = []
    scripted = agent.model
    original = scripted.stream

    async def recording(messages, *a, **kw):
        seen.append([dict(m) for m in messages])
        async for event in original(messages, *a, **kw):
            yield event

    scripted.stream = recording
    assert str(agent("sum them")).strip() == "I will fix that."
    second_request = seen[1]
    results = [block["toolResult"] for m in second_request for block in m["content"] if "toolResult" in block]
    assert results[-1]["status"] == "error"
    assert "NameError: name 'pandas' is not defined" in results[-1]["content"][0]["text"]
    assert t.steps[0]["status"] == "error" and "NameError" in t.steps[0]["error"]
    box.close()


def test_in_the_real_loop_the_budget_ends_the_turn(monkeypatch):
    """Strands invokes the before-tool hook outside the handler that turns a
    tool's failure into an error result, so the hook's BudgetExceeded ends
    the agent call rather than becoming one more tool error. The loop wraps
    it in EventLoopException, which answer() unwraps for the handler."""
    from strands.types.exceptions import EventLoopException

    executes = []
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: "s21"))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: executes.append(code) or "1"))
    monkeypatch.setattr(sandbox.Sandbox, "stop", staticmethod(lambda i, sid: None))
    box, t = sandbox.Sandbox(), trail_module.Trail(max_tool_calls=2)
    agent = _real_agent([("tool", "run_python", {"code": "print(1)"})] * 10, box, t)
    with pytest.raises(EventLoopException) as raised:
        agent("loop")
    assert isinstance(raised.value.original_exception, trail_module.BudgetExceeded)
    assert len(executes) == 2
    assert [s.get("status") for s in t.steps] == ["success", "success", "cancelled", "cancelled"]
    box.close()


def test_answer_unwraps_what_the_loop_wrapped_so_the_handler_sees_the_budget(fakes, monkeypatch):
    """Before this, a spent budget reached the handler as EventLoopException
    and was answered as a plain failure rather than as the budget."""
    from strands.types.exceptions import EventLoopException

    def wrapped(self, prompt):
        raise EventLoopException(trail_module.BudgetExceeded("kept asking"))

    monkeypatch.setattr(FakeAgent, "__call__", wrapped)
    with pytest.raises(trail_module.BudgetExceeded):
        model.answer("loop", "c-1000", "session-1", "minted-token", "sub-1000")
    assert fakes.built[-1].cleaned is True

    def throttled(self, prompt):
        raise EventLoopException(RuntimeError("throttled"))

    monkeypatch.setattr(FakeAgent, "__call__", throttled)
    with pytest.raises(RuntimeError, match="throttled"):
        model.answer("loop", "c-1000", "session-1", "minted-token", "sub-1000")


def test_run_python_is_a_tool_the_model_can_read():
    spec = sandbox.Sandbox().run_python.tool_spec
    assert spec["name"] == "run_python"
    assert "sandbox" in spec["description"]
    assert set(spec["inputSchema"]["json"]["required"]) == {"code"}
