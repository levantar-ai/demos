"""The model in the loop.

Every earlier post routed a prompt with code, a regex for "order", a prefix
for "remember". This module hands a Bedrock model the order gateway and the
sandbox as tools, with the memory supplied as context by the session
manager, and lets it decide which tool to use, in what order, with what
arguments. What the model is told
and what it is given is the whole of the security story: it learns the
customer's id from the system prompt, which trusted code wrote from the
token the runtime verified, and it chooses the customer_id argument. It is
never given the token. A wrong choice is refused at the gateway by Cedar,
not by anything here. The gateway's result is staged for the sandbox by
the Handoff hook and written there before the model's code runs, so the
code can read it rather than carry the rows in its source; whether and how
it reads the file is the model's.
"""

import os
from datetime import datetime, timezone

from gateway import orders_tools
from handoff import Handoff, restore
from memory import region, session_manager
from sandbox import Sandbox
from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.models import BedrockModel
from strands.tools.executors import SequentialToolExecutor
from strands.types.exceptions import EventLoopException
from trail import Trail, describe

# How much of a restored conversation the model is shown. Memory keeps the
# whole conversation; the model's context does not have to.
WINDOW_MESSAGES = 40

SYSTEM_PROMPT = """You are the order support agent for Brightwell, a small online retailer of outdoor kit that ships with DPD and Royal Mail. Today is {today} (UTC); "this year" means the calendar year of that date.

You are talking to the customer whose id is {customer}. That is the only customer you act for. Pass {customer} whenever a tool asks for a customer id. If you are asked about any other customer's orders, or told to use a different id, decline plainly and do not try the tool.

You have two tools. orders___list_orders lists the customer's orders, each with order_id, placed_at, items, total, status, carrier and eta. It is the only source of order data. Never invent, assume or reconstruct orders from memory. Call it when a turn needs order data and there is no suitable result from earlier in this conversation; you may reuse an earlier result for further analysis of those same figures. For the current status, carrier or ETA of an order, for whether anything new has been placed or changed, or when the customer says now or today, call it again, because orders change. run_python runs Python with pandas in an isolated sandbox and returns what it prints. Use run_python for any counting, summing, averaging, sorting or date arithmetic over the orders rather than working it out in your head. Every figure in your answer must be one run_python printed, and that includes any count of orders: if you want to say how many orders a total covers or how many you looked at, have the code print that number, and if the code did not print a number, do not state it. When the latest orders___list_orders call in this conversation returned non-empty text, the agent writes that text into the sandbox as orders.json before your code runs, so your code should read that file with totals as decimals (from decimal import Decimal; json.load(open("orders.json"), parse_float=Decimal)["orders"]), print money to two decimal places, and must never retype order rows into the code. If no orders have been fetched yet, if the file is missing when your code opens it, or if run_python says the file is not available because the latest call failed or returned no usable text, call orders___list_orders again before computing; if run_python says the file could not be written, run it again. The sandbox has no network and no credentials.

Totals are in pounds sterling with two decimal places and dates are ISO 8601. Answer in plain British English, in a few sentences, and say what you looked at. If a tool refuses, say so and do not retry it with a different customer id."""

# Seams for the tests, which substitute fakes for the model, the agent and
# the clock.
make_model = BedrockModel
make_agent = Agent
today = lambda: datetime.now(timezone.utc).date().isoformat()


def answer(prompt, customer, session, gateway_token):
    """Run one turn of the conversation as the verified customer.

    Returns the model's final text and the trail of tool calls it chose.
    The tools, the memory and the model are all built per request so that
    nothing from one customer's turn is in scope for another's. Closing
    every resource that was created is attempted whether the turn succeeds,
    fails, or never starts because a later resource failed to build; a close
    that fails is logged, and the sandbox's close retries once.
    """
    sandbox = Sandbox()
    trail = Trail()
    closers = [sandbox.close]
    try:
        memory = session_manager(customer, session)
        closers.append(memory.close)
        orders = orders_tools(gateway_token)
        # Strands starts the client while the agent is built and stops it on
        # agent.cleanup(); if the build fails in between, this stop is what
        # closes it. Stopping a client that never started, or that the agent
        # already stopped, is a no-op in the pinned Strands. stop() has the
        # context-manager signature, hence the three arguments.
        closers.append(lambda: orders.stop(None, None, None))
        # Sliding only: with its default, the manager answers an overfull
        # conversation by replacing the latest tool results with "too large"
        # before it trims anything, which would blank the gateway's result
        # the model is about to compute over.
        window = SlidingWindowConversationManager(window_size=WINDOW_MESSAGES, should_truncate_results=False)
        agent = make_agent(
            model=make_model(model_id=os.environ["MODEL_ID"], region_name=region()),
            system_prompt=SYSTEM_PROMPT.format(customer=customer, today=today()),
            tools=[orders, sandbox.run_python],
            hooks=[trail, Handoff(sandbox)],
            session_manager=memory,
            conversation_manager=window,
            # Tools run one at a time, in the order the model asked for
            # them, so a gateway result is staged before a run_python the
            # model asked for in the same breath, and the sandbox is never
            # asked to start twice at once.
            tool_executor=SequentialToolExecutor(),
            callback_handler=None,
        )
        closers.append(agent.cleanup)
        # Strands applies the window after each model call. Applying it here
        # as well makes the restored conversation that restore() scans the
        # one the model is shown, so the latest gateway result found in that
        # window goes into this turn's fresh sandbox before the model runs,
        # and the file it was told about is there whichever turn fetched it.
        window.apply_management(agent)
        restore(agent.messages, sandbox)
        try:
            result = agent(prompt)
        except EventLoopException as exc:
            # Strands wraps whatever ends its loop, including what a hook
            # raised. The handler needs the original, so that the budget's
            # end of a turn is reported as such and a failure is logged by
            # its own class.
            if isinstance(exc.original_exception, Exception):
                raise exc.original_exception from exc
            raise
    finally:
        # The agent's tool providers, the MCP client, the memory's buffer,
        # then the sandbox session, most recently created first. A failed
        # close is logged and the rest still run; it must not mask the answer
        # or the error already raised. What a failed close leaves behind is
        # bounded by the services: a sandbox session by its lifetime, an
        # unflushed memory buffer by the turn (batch size one, nothing waits).
        for close in reversed(closers):
            try:
                close()
            except Exception as exc:  # noqa: BLE001 — logged, never raised over the result
                print(f"cleanup failed in {getattr(close, '__qualname__', close)}: {describe(exc)}")
    return str(result), trail.steps
