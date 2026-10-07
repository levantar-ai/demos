"""The gateway's result, handed to the sandbox by trusted code.

The model fetches orders through the gateway and then computes over them in
the sandbox. Left to itself it would carry the rows across by typing them
into the code it writes, which is where a wrong figure would come from with
three hundred rows rather than seven. This hook watches the gateway tool's
result and writes its text, as returned, into the turn's sandbox session as
orders.json, so the model's code can read the file instead of reproducing
the rows in source. The result is still in the model's context, as any tool
result is. A failed write is logged, the turn goes on, and the sandbox tool
refuses to run until the file is written again, so a stale copy from an
earlier turn is never read as the latest result.

The sandbox session is new on every turn while the conversation is restored
from memory, so restore() does the same for the most recent gateway result
in the restored turns before the model runs. The file the model sees is then
always the gateway's latest result in this conversation, whichever turn
fetched it, and a question about the current state still fetches again.
"""

from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry

# Which tool results are handed over, and under what name.
HANDOFFS = {"orders___list_orders": "orders.json"}


def _text_of(result):
    """The text content of a tool result, exactly as returned.

    The gateway returns one text block holding the tool's JSON; that block
    is written without alteration. Several text blocks are joined with
    newlines; non-text content is not carried.
    """
    texts = [item["text"] for item in result.get("content", []) if isinstance(item, dict) and "text" in item]
    return texts[0] if len(texts) == 1 else "\n".join(texts)


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
        if not text.strip():
            return
        try:
            self.sandbox.write(path, text)
        except Exception as exc:  # noqa: BLE001 — the turn continues, but the tool will not run
            # An older copy of the file may be in the session from restore();
            # marking it unavailable stops run_python reading it as current.
            self.sandbox.unavailable.add(path)
            print(f"handoff of {name} to {path} failed: {exc}")
            return
        self.sandbox.unavailable.discard(path)
        self.written.append(path)
        print(f"handed {name} result to the sandbox as {path} ({len(text)} chars)")


def latest_results(messages, handoffs=None):
    """The most recent successful result text per handed-over tool, from a
    restored conversation in Bedrock's message format."""
    handoffs = HANDOFFS if handoffs is None else handoffs
    uses, found = {}, {}

    def _id(block):
        value = block.get("toolUseId")
        return value if isinstance(value, str) and value else None

    for message in messages or []:
        for block in message.get("content", []) or []:
            use = block.get("toolUse") if isinstance(block, dict) else None
            if use and use.get("name") in handoffs and _id(use):
                uses[_id(use)] = use["name"]
            result = block.get("toolResult") if isinstance(block, dict) else None
            if result and result.get("status") == "success" and _id(result) in uses:
                text = _text_of(result)
                if text.strip():
                    found[handoffs[uses[_id(result)]]] = text
    return found


def restore(messages, sandbox, handoffs=None):
    """Write the restored conversation's latest gateway results into the
    sandbox before the model runs. Returns the paths written."""
    written = []
    for path, text in latest_results(messages, handoffs).items():
        try:
            sandbox.write(path, text)
        except Exception as exc:  # noqa: BLE001 — the turn continues, but the tool will not run
            sandbox.unavailable.add(path)
            print(f"restore of {path} to the sandbox failed: {exc}")
            continue
        written.append(path)
        print(f"restored {path} to the sandbox from the conversation ({len(text)} chars)")
    return written
