"""The two isolation properties Cedar does not cover.

Policy in AgentCore refuses a list_orders call whose customer_id differs from
the token's customer_id claim, but it cannot see the rows the tool returns, and the
memory and sandbox paths never pass through the gateway at all. Both rely on
code, so both are tested here against the real implementations. Lives in
agent/ so CI's single pytest run picks it up.
"""

import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tool"))
import memory
import orders

os.environ.setdefault("MEMORY_ID", "mem-test")


# --- the order tool: every row returned belongs to the requested customer ----
def _customers():
    return sorted({r["customer_id"] for r in orders.orders().values()})


def test_the_data_holds_many_customers():
    assert len(_customers()) > 1


@pytest.mark.parametrize("customer_id", ["c-1000", "c-1001"])
def test_list_orders_returns_only_that_customers_rows(customer_id):
    result = orders.list_orders(customer_id)
    assert result["customer_id"] == customer_id
    assert result["orders"], "fixture customers have orders"
    returned = {o["order_id"] for o in result["orders"]}
    expected = {int(r["order_id"]) for r in orders.orders().values()
                if r["customer_id"] == customer_id}
    assert returned == expected
    for o in result["orders"]:
        assert "customer_id" not in o  # never echoed per row


def test_list_orders_for_an_unknown_customer_is_empty_not_everything():
    assert orders.list_orders("c-9999") == {"customer_id": "c-9999", "orders": []}


def test_the_handler_refuses_a_call_without_a_customer():
    assert orders.handler({}, None) == {"error": "expected customer_id"}


def test_no_customer_can_see_the_whole_table():
    total = len(orders.orders())
    for c in _customers():
        assert len(orders.list_orders(c)["orders"]) < total


# --- memory: every call is keyed by the verified customer ----------------------
class _Recorder:
    def __init__(self):
        self.calls = []

    def create_event(self, **kw):
        self.calls.append(("create_event", kw))
        return {}

    def list_events(self, **kw):
        self.calls.append(("list_events", kw))
        return {"events": []}

    def retrieve_memory_records(self, **kw):
        self.calls.append(("retrieve_memory_records", kw))
        return {"memoryRecordSummaries": []}


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(memory, "_client", rec)
    return rec


def test_remember_and_recap_are_keyed_by_the_customer_not_the_session(recorder):
    # A caller controls the session value; it must never widen the actor.
    memory.remember("c-1000", "../c-1001", "remember I like blue")
    memory.recap("c-1000", "../c-1001")
    for name, kw in recorder.calls:
        assert kw["actorId"] == "c-1000", name
        assert kw["sessionId"] == "../c-1001"  # passed through as an opaque id
        assert kw["memoryId"] == "mem-test"


def test_recall_searches_only_the_customers_namespace(recorder):
    memory.recall("c-1000", "colour")
    (name, kw), = recorder.calls
    assert name == "retrieve_memory_records"
    assert kw["namespace"] == "/users/c-1000"
