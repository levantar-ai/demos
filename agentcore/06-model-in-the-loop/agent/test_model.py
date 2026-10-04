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
    def __init__(self, **kw):
        self.kw = kw


class FakeResult:
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return self.text


class FakeAgent:
    built: ClassVar[list] = []

    def __init__(self, **kw):
        self.kw = kw
        self.cleaned = False
        FakeAgent.built.append(self)

    def __call__(self, prompt):
        self.prompt = prompt
        return FakeResult(f"answered: {prompt}")

    def cleanup(self):
        self.cleaned = True


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


def test_the_token_goes_to_the_gateway_client_and_never_to_the_model(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token")
    agent = fakes.built[-1]
    client = next(t for t in agent.kw["tools"] if isinstance(t, FakeClient))
    assert client.kw == {
        "url": "https://gw.example/mcp",
        "headers": {"Authorization": "Bearer minted-token"},
    }
    assert "minted-token" not in agent.kw["system_prompt"]


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


def test_the_trail_is_the_agents_hook(fakes):
    model.answer("my orders", "c-1000", "session-1", "minted-token")
    hooks = fakes.built[-1].kw["hooks"]
    assert len(hooks) == 1 and isinstance(hooks[0], trail_module.Trail)


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
