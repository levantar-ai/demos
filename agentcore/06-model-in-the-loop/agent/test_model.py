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

    def stop(self, *args):
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
        return FakeResult(f"answered: {prompt}")

    def cleanup(self):
        self.cleaned = True
        for t in self.kw.get("tools", []):
            if isinstance(t, FakeClient):
                t.stop()


@pytest.fixture
def fakes(monkeypatch):
    FakeAgent.built.clear()
    monkeypatch.setattr(model, "make_model", FakeModel)
    monkeypatch.setattr(model, "make_agent", FakeAgent)
    monkeypatch.setattr(gateway, "make_client", FakeClient)
    monkeypatch.setattr(memory, "make_manager", FakeManager)
    monkeypatch.setattr(sandbox.Sandbox, "stop", staticmethod(lambda interpreter, sid: None))
    return FakeAgent


def test_the_model_learns_the_customer_from_trusted_code(fakes):
    text, steps = model.answer("how much have I spent?", "c-1000", "session-1", "minted-token")
    agent = fakes.built[-1]
    assert text == "answered: how much have I spent?"
    assert steps == []
    assert "c-1000" in agent.kw["system_prompt"]
    assert "c-1001" not in agent.kw["system_prompt"]


def test_the_model_is_told_the_gateway_is_the_only_source_of_orders(fakes):
    """The live run's lesson: without this the second turn of a conversation
    invented a dataset in the sandbox instead of fetching again."""
    model.answer("which carrier?", "c-1000", "session-1", "minted-token")
    prompt = fakes.built[-1].kw["system_prompt"]
    assert "only source of order data" in prompt
    assert "Never invent" in prompt
    assert "call it again" in prompt  # a restored snapshot is for analysis, not for current status
    assert "Call it in any turn that needs order data" not in prompt  # reuse is allowed for the same figures
    assert "there is no suitable result from earlier in this conversation" in prompt
    assert "current status, carrier or ETA of an order" in prompt


def test_the_token_goes_to_the_gateway_client_and_never_to_the_model(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token")
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
    model.answer("my orders", "c-1000", "session-1", "minted-token")
    client = next(t for t in fakes.built[-1].kw["tools"] if isinstance(t, FakeClient))
    assert client.kw["tool_filters"]["allowed"] == ["orders___list_orders"]


def test_the_model_is_given_the_sandbox_as_a_tool(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token")
    agent = fakes.built[-1]
    names = [getattr(t, "tool_name", None) for t in agent.kw["tools"]]
    assert "run_python" in names


def test_memory_is_keyed_by_the_verified_customer_and_session(fakes):
    model.answer("my orders", "c-1000", "session-42", "minted-token")
    manager = fakes.built[-1].kw["session_manager"]
    assert manager.config.actor_id == "c-1000"
    assert manager.config.session_id == "session-42"
    assert manager.config.memory_id == "mem-test"
    assert list(manager.config.retrieval_config) == ["/users/{actorId}"]
    assert manager.region_name == "us-east-1"
    assert manager.closed is True


def test_the_model_id_and_region_come_from_the_environment(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token")
    assert fakes.built[-1].kw["model"].kw == {
        "model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "region_name": "us-east-1",
    }


def test_the_agent_is_cleaned_up_even_when_the_turn_fails(fakes, monkeypatch):
    def fail(self, prompt):
        raise RuntimeError("throttled")

    monkeypatch.setattr(FakeAgent, "__call__", fail)
    with pytest.raises(RuntimeError, match="throttled"):
        model.answer("my orders", "c-1000", "session-1", "minted-token")
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
        model.answer("my orders", "c-1000", "session-1", "minted-token")
    assert clients[-1].stopped == 1 and clients[-1].started is False


def test_the_mcp_client_is_stopped_once_on_the_happy_path(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token")
    client = next(t for t in fakes.built[-1].kw["tools"] if isinstance(t, FakeClient))
    assert client.stopped == 1  # agent.cleanup stopped it; the extra stop was a no-op


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
        model.answer("my orders", "c-1000", "session-1", "minted-token")
    assert managers and managers[-1].closed is True


def test_a_failing_close_does_not_stop_the_others_or_mask_the_answer(fakes, monkeypatch, capsys):
    monkeypatch.setattr(FakeManager, "close", lambda self: (_ for _ in ()).throw(RuntimeError("flush failed")))
    text, _ = model.answer("my orders", "c-1000", "session-1", "minted-token")
    assert text == "answered: my orders"
    assert fakes.built[-1].cleaned is True
    assert "cleanup failed" in capsys.readouterr().out


def test_the_trail_and_the_handoff_are_the_agents_hooks(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token")
    hooks = fakes.built[-1].kw["hooks"]
    assert [type(h) for h in hooks] == [trail_module.Trail, handoff.Handoff]
    assert hooks[1].sandbox is not None


def test_the_model_is_told_to_read_the_file_not_retype_rows(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token")
    prompt = fakes.built[-1].kw["system_prompt"]
    assert "orders.json" in prompt and "never retype order rows" in prompt
    assert "returned non-empty text and the agent successfully wrote it" in prompt
    assert "call orders___list_orders again before computing" in prompt


def _conversation_with_a_fetch(text):
    return [
        {"role": "user", "content": [{"text": "how much have I spent?"}]},
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t1", "name": "orders___list_orders", "input": {"customer_id": "c-1000"}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t1", "status": "success", "content": [{"text": text}]}}]},
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t2", "name": "run_python", "input": {"code": "print(1)"}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t2", "status": "success", "content": [{"text": "1"}]}}]},
        {"role": "assistant", "content": [{"text": "£743.80"}]},
    ]


def test_a_restored_conversations_latest_fetch_is_put_in_the_sandbox_before_the_model_runs(fakes, monkeypatch):
    """The live run's second turn read orders.json before fetching and found
    nothing, because the sandbox session is new each turn. Trusted code now
    restores the last gateway result into it first."""
    text = '{"customer_id": "c-1000", "orders": [{"order_id": 1033, "total": 12.0}]}'
    puts = []
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: "s5"))
    monkeypatch.setattr(sandbox.Sandbox, "put", staticmethod(lambda sid, path, t: puts.append((path, t))))
    monkeypatch.setattr(FakeAgent, "restored_messages", _conversation_with_a_fetch(text))
    try:
        model.answer("which carrier?", "c-1000", "session-1", "minted-token")
    finally:
        monkeypatch.setattr(FakeAgent, "restored_messages", [])
    assert puts == [("orders.json", text)]


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
    with pytest.raises(RuntimeError, match="orders.json could not be written"):
        box.run_python(code="print(1)")
    later = msgs + [
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t6", "name": "orders___list_orders", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t6", "status": "success", "content": [{"text": "new rows"}]}}]},
    ]
    box2 = sandbox.Sandbox()
    assert handoff.restore(later, box2) == ["orders.json"]
    assert box2.unavailable == set() and box2.run_python(code="print(1)") == "ran"


def test_blocks_without_a_tool_use_id_are_never_matched():
    msgs = [
        {"role": "assistant", "content": [{"toolUse": {"name": "orders___list_orders", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"status": "success", "content": [{"text": "rows"}]}}]},
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "", "name": "orders___list_orders", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "", "status": "success", "content": [{"text": "rows"}]}}]},
        {"role": "user", "content": ["not a block", {"text": "plain"}]},
    ]
    assert handoff.latest_results(msgs) == {}


def test_a_failed_restore_is_logged_and_the_turn_goes_on(capsys):
    assert handoff.restore(_conversation_with_a_fetch("x"), _Box(fail=True)) == []
    assert "restore of orders.json to the sandbox failed" in capsys.readouterr().out


# --- the handoff: the gateway's result reaches the sandbox untouched ---------
class _Box:
    def __init__(self, fail=False):
        self.files, self.fail, self.unavailable = [], fail, set()

    def write(self, path, text):
        if self.fail:
            raise RuntimeError("session unavailable")
        self.files.append((path, text))


def test_a_successful_gateway_result_is_written_to_the_sandbox_exactly_as_returned(capsys):
    box = _Box()
    h = handoff.Handoff(box)
    text = '  {"customer_id": "c-1000", "orders": [{"order_id": 1033, "total": 12.0}]}\n'
    h.after(_Event({"name": "orders___list_orders", "input": {"customer_id": "c-1000"}, "toolUseId": "u1"},
                   {"status": "success", "content": [{"text": text}]}))
    assert box.files == [("orders.json", text)]  # whitespace and all
    assert h.written == ["orders.json"]
    assert "1033" not in capsys.readouterr().out  # the log line carries the size, not the rows


def test_several_text_blocks_are_joined_and_other_content_dropped():
    box = _Box()
    handoff.Handoff(box).after(_Event({"name": "orders___list_orders", "input": {}, "toolUseId": "u1"},
                                      {"status": "success", "content": [{"text": "a"}, {"image": {}}, {"text": "b"}]}))
    assert box.files == [("orders.json", "a\nb")]


def test_a_failed_refresh_makes_the_tool_refuse_rather_than_read_a_stale_file(monkeypatch):
    """restore() put last turn's file in place; the new gateway result could
    not be written; run_python must not compute over the old copy."""
    puts, attempts = [], []

    def flaky_put(sid, path, text):
        attempts.append(text)
        if len(attempts) == 2:
            raise RuntimeError("write failed")
        puts.append((path, text))

    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: "s8"))
    monkeypatch.setattr(sandbox.Sandbox, "put", staticmethod(flaky_put))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: "ran"))
    box = sandbox.Sandbox()
    assert handoff.restore(_conversation_with_a_fetch("old rows"), box) == ["orders.json"]
    h = handoff.Handoff(box)
    h.after(_Event({"name": "orders___list_orders", "input": {}, "toolUseId": "u9"},
                   {"status": "success", "content": [{"text": "new rows"}]}))
    assert box.unavailable == {"orders.json"}
    with pytest.raises(RuntimeError, match="orders.json could not be written"):
        box.run_python(code="print(1)")
    h.after(_Event({"name": "orders___list_orders", "input": {}, "toolUseId": "u10"},
                   {"status": "success", "content": [{"text": "new rows"}]}))
    assert box.unavailable == set() and puts[-1] == ("orders.json", "new rows")
    assert box.run_python(code="print(1)") == "ran"


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
        with pytest.raises(RuntimeError, match="orders.json could not be written"):
            box.run_python(code="print(1)")


def test_the_tool_description_tells_the_model_to_read_the_file_not_embed_rows():
    description = " ".join(sandbox.Sandbox().run_python.tool_spec["description"].split())
    assert "orders.json" in description
    assert "Never put order rows into the code" in description
    assert "returned non-empty text and the agent successfully wrote it" in description
    assert "refuses to run until orders___list_orders is called again" in description
    assert "list of dicts" not in description and "into the code itself" not in description


def test_other_tools_and_failed_calls_are_not_handed_over():
    box = _Box()
    h = handoff.Handoff(box)
    h.after(_Event({"name": "run_python", "input": {"code": "print(1)"}, "toolUseId": "u1"},
                   {"status": "success", "content": [{"text": "1"}]}))
    assert box.unavailable == set()  # an unrelated tool changes nothing
    h.after(_Event({"name": "orders___list_orders", "input": {"customer_id": "c-1001"}, "toolUseId": "u2"},
                   {"status": "error", "content": [{"text": "Tool Execution Denied"}]}))
    assert box.files == [] and h.written == []
    assert box.unavailable == {"orders.json"}  # a failed call withholds any older copy


def test_a_failed_handoff_is_logged_and_does_not_break_the_turn(capsys):
    h = handoff.Handoff(_Box(fail=True))
    h.after(_Event({"name": "orders___list_orders", "input": {}, "toolUseId": "u1"},
                   {"status": "success", "content": [{"text": "{}"}]}))
    assert h.written == []
    assert "handoff of orders___list_orders to orders.json failed" in capsys.readouterr().out


def test_sandbox_write_starts_the_session_and_puts_the_file(monkeypatch):
    started, puts = [], []
    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: started.append(n) or "s3"))
    monkeypatch.setattr(sandbox.Sandbox, "put", staticmethod(lambda sid, path, text: puts.append((sid, path, text))))
    box = sandbox.Sandbox()
    box.write("orders.json", "{}")
    box.write("orders.json", "{}")
    assert started == ["analysis"] and puts == [("s3", "orders.json", "{}")] * 2


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
    assert t.steps == [
        {"tool": "orders___list_orders", "input": {"customer_id": "c-1001"}, "status": "error",
         "error": "Tool Execution Denied: policy"},
        {"tool": "run_python", "input": {"code": "print(1)"}, "status": "success"},
    ]
    assert json.dumps(t.steps)  # what the handler returns must serialise


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
        model.answer("loop forever", "c-1000", "session-1", "minted-token")
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


def test_a_failed_stop_keeps_the_session_id_for_a_retry(monkeypatch):
    attempts = []

    def flaky_stop(interpreter, sid):
        attempts.append(sid)
        if len(attempts) == 1:
            raise RuntimeError("throttled")

    monkeypatch.setattr(sandbox.Sandbox, "start", staticmethod(lambda i, n: "s7"))
    monkeypatch.setattr(sandbox.Sandbox, "execute", staticmethod(lambda sid, code: "ok"))
    monkeypatch.setattr(sandbox.Sandbox, "stop", staticmethod(flaky_stop))
    box = sandbox.Sandbox()
    box.run_python(code="print(1)")
    with pytest.raises(RuntimeError):
        box.close()
    assert box.session_id == "s7"
    box.close()
    assert box.session_id is None and attempts == ["s7", "s7"]


def test_closing_an_unused_sandbox_stops_nothing(monkeypatch):
    stopped = []
    monkeypatch.setattr(sandbox.Sandbox, "stop", staticmethod(lambda interpreter, sid: stopped.append(sid)))
    sandbox.Sandbox().close()
    assert stopped == []


def test_run_python_is_a_tool_the_model_can_read():
    spec = sandbox.Sandbox().run_python.tool_spec
    assert spec["name"] == "run_python"
    assert "sandbox" in spec["description"]
    assert set(spec["inputSchema"]["json"]["required"]) == {"code"}
