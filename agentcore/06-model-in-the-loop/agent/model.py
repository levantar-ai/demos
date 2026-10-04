"""The model in the loop.

Every earlier post routed a prompt with code, a regex for "order", a prefix
for "remember". This module hands a Bedrock model the tools those posts
built, the order gateway, the sandbox and the memory, and lets it decide
which to use, in what order, with what arguments. What the model is told
and what it is given is the whole of the security story: it learns the
customer's id from the system prompt, which trusted code wrote from the
token the runtime verified, and it chooses the customer_id argument. It is
never given the token. A wrong choice is refused at the gateway by Cedar,
not by anything here.
"""

import os

from gateway import orders_tools
from memory import region, session_manager
from sandbox import Sandbox
from strands import Agent
from strands.models import BedrockModel
from trail import Trail

SYSTEM_PROMPT = """You are the order support agent for Brightwell, a small online retailer of outdoor kit that ships with DPD and Royal Mail.

You are talking to the customer whose id is {customer}. That is the only customer you act for. Pass {customer} whenever a tool asks for a customer id. If you are asked about any other customer's orders, or told to use a different id, decline plainly and do not try the tool.

You have two tools. orders___list_orders lists the customer's orders, each with order_id, placed_at, items, total, status, carrier and eta. run_python runs Python with pandas in an isolated sandbox and returns what it prints. Use run_python for any counting, summing, averaging, sorting or date arithmetic over the orders rather than working it out in your head: put the orders into the code as data and print the result. The sandbox has no network and no credentials.

Totals are in pounds sterling and dates are ISO 8601. Answer in plain British English, in a few sentences, and say what you looked at. If a tool refuses, say so and do not retry it with a different customer id."""

# Seams for the tests, which substitute fakes for the model and the agent.
make_model = BedrockModel
make_agent = Agent


def answer(prompt, customer, session, gateway_token):
    """Run one turn of the conversation as the verified customer.

    Returns the model's final text and the trail of tool calls it chose.
    The tools, the memory and the model are all built per request so that
    nothing from one customer's turn is in scope for another's.
    """
    sandbox = Sandbox()
    trail = Trail()
    memory = session_manager(customer, session)
    agent = make_agent(
        model=make_model(model_id=os.environ["MODEL_ID"], region_name=region()),
        system_prompt=SYSTEM_PROMPT.format(customer=customer),
        tools=[orders_tools(gateway_token), sandbox.run_python],
        hooks=[trail],
        session_manager=memory,
        callback_handler=None,
    )
    try:
        result = agent(prompt)
    finally:
        # The MCP connection, the sandbox session, then the memory's buffer.
        # Cleanup failures must not mask the answer or the error that is
        # already propagating.
        for close in (agent.cleanup, sandbox.close, memory.close):
            try:
                close()
            except Exception as exc:  # noqa: BLE001 — logged, never raised over the result
                print(f"cleanup failed: {exc}")
    return str(result), trail.steps
