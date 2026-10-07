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
MAX_TOOL_CALLS attempts, counted as the model asks and whether or not the
tool then succeeds, the next request is cancelled with a message that tells
the model to answer from what it has, recorded in the trail as cancelled,
and a request after that ends the turn with BudgetExceeded, which the
handler turns into a 502. Cancelling alone would not bound anything, the
model could keep asking and each ask is another model invocation.

describe() is what every failure looks like in the log: the exception's
class and, for an AWS error, its code, never its message, which can carry
a response body, a token or the model's code.
"""


import threading

from strands.hooks import (
    AfterToolCallEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)

ERROR_PREVIEW = 300
MAX_TOOL_CALLS = 8


class BudgetExceeded(RuntimeError):
    """The model kept asking for tools after being told the budget was spent."""


def describe(exc):
    """A failure as the log may carry it: class and AWS error code only."""
    response = getattr(exc, "response", None)
    code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
    return f"{type(exc).__name__}" + (f" {code}" if isinstance(code, str) and code else "")


def _text_of(result):
    """The text of a result, or nothing for a malformed one, so a tool
    failure the hook is recording is not turned into a failed turn."""
    content = result.get("content") if isinstance(result, dict) else None
    if not isinstance(content, list):
        return ""
    return " ".join(
        item["text"] for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)
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
        self.executed = 0
        self._open = {}
        # The count and the open steps are shared by every tool call's
        # hooks; the agent runs tools one at a time, and the lock keeps the
        # budget exact if that ever changes.
        self._lock = threading.Lock()

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before)
        registry.add_callback(AfterToolCallEvent, self.after)

    def before(self, event):
        with self._lock:
            self._before(event)

    def after(self, event):
        with self._lock:
            self._after(event)

    def _before(self, event):
        use = event.tool_use
        step = {"tool": use["name"], "input": use.get("input", {})}
        if self.executed >= self.max_tool_calls:
            refused = sum(1 for s in self.steps if s.get("status") == "cancelled")
            step["status"] = "cancelled"
            self.steps.append(step)
            print(f"tool budget spent, refused {use['name']}")
            if refused >= 1:
                raise BudgetExceeded(
                    f"the model asked for a tool again after the budget of {self.max_tool_calls} was spent"
                )
            event.cancel_tool = (
                f"tool budget of {self.max_tool_calls} calls for this turn is spent; "
                "answer with what you have"
            )
            return
        self.executed += 1
        self.steps.append(step)
        self._open[use.get("toolUseId")] = step
        print(f"model chose {use['name']} (input {_size_of(step['input'])} chars)")

    def _after(self, event):
        use = event.tool_use
        step = self._open.pop(use.get("toolUseId"), None)
        if step is None:
            return
        result = event.result or {}
        step["status"] = result.get("status", "unknown")
        if step["status"] != "success":
            step["error"] = _text_of(result)[:ERROR_PREVIEW]
        print(f"{use['name']} returned {step['status']}")
