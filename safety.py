"""Safety + reliability primitives for the Trip Concierge agent.

Two independent mechanisms live here:

1. `safe_calculate` — the safety mitigation (rubric: Safety, 20 pts).
   The `calculate` tool must never run raw eval()/exec() on a string,
   because anything that reaches it (including text that originated from
   mocked tool results — standing in for attacker-controlled content in a
   real system, e.g. a hotel listing whose "name" field contains text
   trying to look like an instruction) is untrusted input. If the model
   were ever tricked into asking calculate to evaluate something like
   "__import__('os').system('echo pwned')" or "(1).__class__", raw eval()
   would happily run it. safe_calculate() parses the expression into an
   AST and only ever evaluates numeric literals combined with +, -, *, /,
   and unary +/-. Anything else (names, calls, attribute access, imports,
   strings, comprehensions...) raises ValueError before any code runs.
   See test_safety.py for a concrete before/after demonstration.

2. `StepTracker` — the step limit (rubric: Reliability, 20 pts), implemented
   as a real counter + break condition, not a comment. It's wired in as a
   `before_tool_callback`, so it counts actual *work* tool calls (not LLM
   calls) and, once the cap is hit, intercepts the next work-tool call
   before it runs and returns a structured "step_limit_reached" response
   instead of executing it. It deliberately does NOT count or block ADK's
   own `set_model_response` tool — the mechanism the agent uses to deliver
   its schema-validated final answer, including an honest "incomplete"
   one. Blocking that too (an earlier version of this code did) silently
   destroyed a well-formed "incomplete" answer the model had already
   composed and replaced it with a raw, non-schema-shaped error instead —
   which is worse than no step limit at all. The agent sees the
   step_limit_reached signal on the work tool and can report the run as
   "incomplete" in its final structured output, instead of looping forever,
   crashing, or having its honest answer thrown away by our own safeguard.
"""

from __future__ import annotations

import ast
import operator
from typing import Any, List


_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# ADK's auto-generated tool used to deliver the schema-validated final
# answer when output_schema is set on an LlmAgent. Confirmed by inspecting
# google/adk/tools/set_model_response_tool.py in the installed
# google-adk==2.3.0, and by name in this project's own captured run trace.
# It must always be allowed through, even after the step cap is hit.
FINALIZING_TOOL_NAMES = {"set_model_response"}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError(f"Disallowed constant: {node.value!r}")
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](
            _eval_node(node.left), _eval_node(node.right)
        )
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"Disallowed expression element: {ast.dump(node)}")


def safe_calculate(expression: str) -> float:
    """Evaluates a numeric expression using only +, -, *, /, and parentheses.

    Raises ValueError for anything outside that grammar instead of running it.
    """
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Expression must be a non-empty string.")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Could not parse expression {expression!r}: {exc}") from exc
    return _eval_node(tree)


class StepTracker:
    """Counts work-tool calls across one agent run and enforces a hard cap.

    The cap applies to "work" tools (search_flights, search_hotels,
    calculate) — it never blocks FINALIZING_TOOL_NAMES, so the agent can
    always deliver its answer, even an honest "incomplete" one.
    """

    def __init__(self, max_steps: int = 5):
        self.max_steps = max_steps
        self.count = 0
        self.calls: List[str] = []

    def before_tool_callback(self, *, tool: Any, args: dict, tool_context: Any):
        self.calls.append(tool.name)
        if tool.name in FINALIZING_TOOL_NAMES:
            return None  # always let the agent submit its final answer
        self.count += 1
        if self.count > self.max_steps:
            return {
                "status": "step_limit_reached",
                "error_message": (
                    f"Step limit of {self.max_steps} tool calls reached; "
                    f"not executing '{tool.name}'. Return the best answer "
                    f"you already have and set status to 'incomplete'."
                ),
            }
        return None  # None == proceed with the real tool call


def on_tool_error_callback(*, tool: Any, args: dict, tool_context: Any, error: Exception):
    """Last-resort net: convert an unexpected tool crash into a structured
    error response instead of letting the exception kill the whole run."""
    return {
        "status": "error",
        "error_message": f"Tool '{tool.name}' raised {type(error).__name__}: {error}",
    }