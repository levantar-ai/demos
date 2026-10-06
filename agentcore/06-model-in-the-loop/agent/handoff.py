"""The gateway's result, handed to the sandbox by trusted code.

The model fetches orders through the gateway and then computes over them in
the sandbox. Left to itself it would carry the rows across by typing them
into the code it writes, which is where a wrong figure would come from with
three hundred rows rather than seven. This hook watches the gateway tool's
result and writes it, byte for byte, into the turn's sandbox session as
orders.json, so the model's code reads the file and the data path never
passes through the model. A failed handoff is logged and the turn goes on;
the model still has the result in its context.
"""

from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry

# Which tool results are handed over, and under what name.
HANDOFFS = {"orders___list_orders": "orders.json"}


def _text_of(result):
    return "\n".join(
        item["text"] for item in result.get("content", []) if isinstance(item, dict) and "text" in item
    ).strip()


class Handoff(HookProvider):
    def __init__(self, sandbox, handoffs=None):
        self.sandbox = sandbox
        self.handoffs = dict(HANDOFFS if handoffs is None else handoffs)
        self.written = []

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(AfterToolCallEvent, self.after)

    def after(self, event):
        name = event.tool_use.get("name")
        path = self.handoffs.get(name)
        result = event.result or {}
        if path is None or result.get("status") != "success":
            return
        text = _text_of(result)
        if not text:
            return
        try:
            self.sandbox.write(path, text)
        except Exception as exc:  # noqa: BLE001 — the turn continues without the file
            print(f"handoff of {name} to {path} failed: {exc}")
            return
        self.written.append(path)
        print(f"handed {name} result to the sandbox as {path} ({len(text)} chars)")
