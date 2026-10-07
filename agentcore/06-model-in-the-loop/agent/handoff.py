"""The gateway's result, handed to the sandbox by trusted code.

The model fetches orders through the gateway and then computes over them in
the sandbox. Left to itself it would carry the rows across by typing them
into the code it writes, which is where a wrong figure would come from with
three hundred rows rather than seven. This hook watches the gateway tool's
result and writes its text, as returned, into the turn's sandbox session as
orders.json, so the model's code can read the file instead of reproducing
the rows in source. The result is still in the model's context, as any tool
result is. Three outcomes withhold the file instead: the call failed, it
returned no text, or the write failed. Each is logged, the turn goes on,
and the sandbox tool refuses to run until a later call's result is written,
so a copy from an earlier turn is not read as the latest result.

The sandbox session is new on every turn while the conversation is restored
from memory, so restore() rebuilds that state from the restored tool history
before the model runs: it writes the file whose latest call succeeded and
withholds the file whose latest call did not. Whether and how the model's
code reads the file is the model's choice, and a question about the current
state still fetches again.
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
        if path is None:
            return
        # Any call to a handed-over tool invalidates the file until a new
        # result has been written. An older copy may be in the session from
        # restore(); a failed call, an empty result or a failed write must
        # not leave it readable as if it were the latest.
        self.sandbox.unavailable.add(path)
        result = event.result or {}
        if result.get("status") != "success":
            print(f"{name} did not succeed, {path} withheld")
            return
        text = _text_of(result)
        if not text.strip():
            print(f"{name} returned no text, {path} withheld")
            return
        try:
            self.sandbox.write(path, text)
        except Exception as exc:  # noqa: BLE001 — the turn continues, but the tool will not run
            print(f"handoff of {name} to {path} failed: {exc}")
            return
        self.sandbox.unavailable.discard(path)
        self.written.append(path)
        print(f"handed {name} result to the sandbox as {path} ({len(text)} chars)")


def latest_results(messages, handoffs=None):
    """The latest outcome per handed-over tool in a restored conversation.

    Maps each file to the text of the most recent call's result when that
    call succeeded with text, and to None when the most recent call failed
    or returned nothing, so that a later turn withholds the file the same
    way the turn that saw the failure did. Tools never called are absent.
    """
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
            if result and _id(result) in uses:
                path = handoffs[uses[_id(result)]]
                text = _text_of(result) if result.get("status") == "success" else ""
                found[path] = text if text.strip() else None
    return found


def restore(messages, sandbox, handoffs=None):
    """Bring the restored conversation's handoff state into this turn's
    sandbox before the model runs: write each file whose latest call
    succeeded, and withhold each whose latest call did not. Returns the
    paths written."""
    written = []
    for path, text in latest_results(messages, handoffs).items():
        if text is None:
            sandbox.unavailable.add(path)
            print(f"{path} withheld: the conversation's latest call for it did not produce a result")
            continue
        try:
            sandbox.write(path, text)
        except Exception as exc:  # noqa: BLE001 — the turn continues, but the tool will not run
            sandbox.unavailable.add(path)
            print(f"restore of {path} to the sandbox failed: {exc}")
            continue
        sandbox.unavailable.discard(path)
        written.append(path)
        print(f"restored {path} to the sandbox from the conversation ({len(text)} chars)")
    return written
