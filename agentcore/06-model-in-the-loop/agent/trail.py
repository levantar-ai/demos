"""What the model decided, in the order it decided it.

A Strands hook that records every tool call the model makes, with the
arguments it chose and whether the tool succeeded. The handler returns it
with the answer so a caller can see the route the model took, which is the
point of this post, and prints each step so the runtime's log shows the
same thing. Nothing here changes what the model does.
"""

from strands.hooks import (
    AfterToolCallEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)

ERROR_PREVIEW = 300


def _text_of(result):
    return " ".join(
        item["text"] for item in result.get("content", []) if isinstance(item, dict) and "text" in item
    ).strip()


class Trail(HookProvider):
    def __init__(self):
        self.steps = []
        self._open = {}

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before)
        registry.add_callback(AfterToolCallEvent, self.after)

    def before(self, event):
        use = event.tool_use
        step = {"tool": use["name"], "input": use.get("input", {})}
        self.steps.append(step)
        self._open[use.get("toolUseId")] = step
        print(f"model chose {use['name']} with {step['input']}")

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
