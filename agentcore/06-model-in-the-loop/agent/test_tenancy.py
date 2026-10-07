"""The two isolation properties Cedar does not cover.

Policy in AgentCore refuses a list_orders call whose customer_id differs from
the token's customer_id claim, but it cannot see the rows the tool returns, and
the memory never passes through the gateway at all. Both rely on code, so both
are tested here against the real implementations. Lives in agent/ so CI's
single pytest run picks it up.
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


# --- memory: every conversation is keyed by the verified customer -------------
def test_memory_is_configured_for_the_customer_not_a_body_value():
    # A caller controls the session value; it must never widen the actor.
    config = memory.config_for("c-1000", "../c-1001")
    assert config.actor_id == "c-1000"
    assert config.session_id == "../c-1001"  # passed through as an opaque id
    assert config.memory_id == "mem-test"


def test_recall_searches_only_the_customers_namespace():
    config = memory.config_for("c-1000", "s")
    (namespace,) = config.retrieval_config
    assert namespace == "/users/{actorId}"
    assert namespace.format(actorId=config.actor_id) == "/users/c-1000"


# --- what the Terraform fixes that the code relies on -------------------------
TERRAFORM = pathlib.Path(__file__).resolve().parents[1] / "terraform"


def test_the_sandbox_has_no_network():
    """SANDBOX mode is what lets the model's code run at all."""
    assert 'network_mode = "SANDBOX"' in (TERRAFORM / "tools.tf").read_text()


def test_the_execution_roles_trust_the_service_only_for_this_demos_runtime_and_gateway():
    assert "runtime/${local.runtime_name}-*" in (TERRAFORM / "iam.tf").read_text()
    assert "gateway/${local.name_prefix}-gw-*" in (TERRAFORM / "gateway.tf").read_text()
