"""What the model decided, in the order it decided it, and how much of it.

A Strands hook that records every tool call the model makes, with the
arguments it chose and whether the tool succeeded. The handler returns it
with the answer, to the customer whose data it is, so a caller can see the
route the model took, which is the point of this post. The runtime log gets
a redacted line per step, tool name, status and the size of the input, never
the input itself, so generated code and the order rows it embeds do not land
in CloudWatch.

The same hook is the turn's budget. A model loop that keeps calling tools is
a cost and an availability problem before it is anything else, so after
MAX_TOOL_CALLS the hook cancels further calls and the model is told why.
"""

from strands.hooks import (
    AfterToolCallEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)

ERROR_PREVIEW = 300
MAX_TOOL_CALLS = 8


def _text_of(result):
    return " ".join(
        item["text"] for item in result.get("content", []) if isinstance(item, dict) and "text" in item
    ).strip()


def _size_of(value):
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(_size_of(v) for v in value.values())
    return len(str(value))


class Trail(HookProvider):
    def __init__(self, max_tool_calls=MAX_TOOL_CALLS):
        self.steps = []
        self.max_tool_calls = max_tool_calls
        self._open = {}

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before)
        registry.add_callback(AfterToolCallEvent, self.after)

    def before(self, event):
        use = event.tool_use
        if len(self.steps) >= self.max_tool_calls:
            event.cancel_tool = (
                f"tool budget of {self.max_tool_calls} calls for this turn is spent; "
                "answer with what you have"
            )
            print(f"tool budget spent, refused {use['name']}")
            return
        step = {"tool": use["name"], "input": use.get("input", {})}
        self.steps.append(step)
        self._open[use.get("toolUseId")] = step
        print(f"model chose {use['name']} (input {_size_of(step['input'])} chars)")

    def after(self, event):
        use = event.tool_use
        step = self._open.pop(use.get("toolUseId"), None)
        if step is None:
            return
        result = event.result or {}
        step["status"] = result.get("status", "unknown")
        if step["status"] != "success":
            step["error"] = _text_of(result)[:ERROR_PREVIEW]
        print(f"{use['name']} returned {step['status']}")
