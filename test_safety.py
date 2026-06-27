"""Demonstrates the safety mitigation with a real before/after — this is
the evidence for the README's safety note, captured without needing the
live model at all, since the vulnerability and the fix are both pure
Python logic, not model behavior.

"Before": calculate() implemented with raw eval() (what NOT to do).
"After":  calculate() implemented with safe_calculate() (what we ship).

Both are fed the same adversarial input: a string that, if it ever reached
eval(), would execute arbitrary Python. This stands in for a prompt-
injection scenario where attacker-controlled text (e.g. a poisoned hotel
listing) gets passed into the calculate tool's `expression` argument.

Run with: python3 test_safety.py
"""

from safety import safe_calculate

MALICIOUS_INPUT = "__import__('os').system('echo pwned-via-calculate') or 1"


def before_unsafe_eval(expression: str):
    """This is what calculate() would look like WITHOUT the mitigation."""
    return eval(expression)  # noqa: S307 - intentionally unsafe, for the demo only


def after_safe_calculate(expression: str):
    """This is the actual calculate() implementation we ship."""
    return safe_calculate(expression)


if __name__ == "__main__":
    print("Adversarial input:", repr(MALICIOUS_INPUT))

    print("\n--- BEFORE (raw eval) ---")
    try:
        result = before_unsafe_eval(MALICIOUS_INPUT)
        print(f"eval() executed the payload. Result: {result!r}")
        print("(You should see a 'pwned-via-calculate' line printed above this — "
              "that's a shell command that ran because of unvalidated input.)")
    except Exception as exc:
        print(f"eval() raised {type(exc).__name__}: {exc}")

    print("\n--- AFTER (safe_calculate) ---")
    try:
        result = after_safe_calculate(MALICIOUS_INPUT)
        print(f"UNEXPECTED: safe_calculate returned {result!r} instead of rejecting it.")
    except ValueError as exc:
        print(f"Rejected as expected: ValueError: {exc}")

    print("\n--- Sanity check: legitimate arithmetic still works ---")
    print("safe_calculate('58.0 + 65.0 * 3') ->", safe_calculate("58.0 + 65.0 * 3"))