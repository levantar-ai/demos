"""The gateway's result, handed to the sandbox by trusted code.

The model fetches orders through the gateway and then computes over them in
the sandbox. Left to itself it would carry the rows across by typing them
into the code it writes, which is where a wrong figure would come from with
three hundred rows rather than seven. This hook watches the gateway tool's
result and stages its text, as returned, for the turn's sandbox under the
name orders.json; the sandbox writes it into its session just before the
model's code next runs, so the code can read the file instead of
reproducing the rows in source, and a turn in which the model never runs
code starts no session. The result is still in the model's context, as any
tool result is. A call that failed or returned no text withholds the file
instead: it is logged, the turn goes on, and the sandbox tool refuses to
run until a later call's result is staged, so a copy from an earlier turn
is not read as the latest result. A write that fails when the code runs is
reported to the model as the tool's error and tried again on its next call.

The sandbox session is new on every turn while the conversation is restored
from memory, so restore() rebuilds that state from the restored tool history
before the model runs: it stages the file whose latest call succeeded and
withholds the file whose latest call did not. Whether and how the model's
code reads the file is the model's choice, and a question about the current
state still fetches again.
"""

from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry

# Which tool results are handed over, and under what name.
HANDOFFS = {"orders___list_orders": "orders.json"}
# A result larger than this is withheld rather than staged: the gateway's
# orders for one customer are kilobytes, and a result that is not cannot be
# the thing the model was asked to compute over.
MAX_HANDOFF_CHARS = 200_000


def _text_of(result):
    """The text content of a tool result, exactly as returned.

    The gateway returns one text block holding the tool's JSON; that block
    is carried without alteration. Several text blocks are joined with
    newlines; non-text content is not carried, and a malformed result, one
    whose content is not a list or whose text is not a string, reads as no
    text rather than as an error in the hook.
    """
    content = result.get("content") if isinstance(result, dict) else None
    if not isinstance(content, list):
        return ""
    texts = [item["text"] for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)]
    return texts[0] if len(texts) == 1 else "\n".join(texts)


class Handoff(HookProvider):
    def __init__(self, sandbox, handoffs=None):
        self.sandbox = sandbox
        self.handoffs = dict(HANDOFFS if handoffs is None else handoffs)
        self.staged = []

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(AfterToolCallEvent, self.after)

    def after(self, event):
        name = event.tool_use.get("name")
        path = self.handoffs.get(name)
        if path is None:
            return
        # Any call to a handed-over tool withholds the file until a new
        # result has been staged. An older copy may be in the session from
        # an earlier run this turn; a failed call or an empty result must
        # not leave it readable as if it were the latest.
        self.sandbox.withhold(path)
        result = event.result or {}
        if result.get("status") != "success":
            print(f"{name} did not succeed, {path} withheld")
            return
        text = _text_of(result)
        if not text.strip():
            print(f"{name} returned no text, {path} withheld")
            return
        if len(text) > MAX_HANDOFF_CHARS:
            print(f"{name} returned {len(text)} chars, over the {MAX_HANDOFF_CHARS} limit, {path} withheld")
            return
        self.sandbox.stage(path, text)
        self.staged.append(path)
        print(f"staged {name} result for the sandbox as {path} ({len(text)} chars)")


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
                found[path] = text if text.strip() and len(text) <= MAX_HANDOFF_CHARS else None
    return found


def restore(messages, sandbox, handoffs=None):
    """Bring the restored conversation's handoff state into this turn's
    sandbox before the model runs: stage each file whose latest call
    succeeded, and withhold each whose latest call did not. Returns the
    paths staged. Nothing is written until the model's code runs."""
    staged = []
    for path, text in latest_results(messages, handoffs).items():
        if text is None:
            sandbox.withhold(path)
            print(f"{path} withheld: the conversation's latest call for it did not produce a result")
            continue
        sandbox.stage(path, text)
        staged.append(path)
        print(f"restored {path} for the sandbox from the conversation ({len(text)} chars)")
    return staged
