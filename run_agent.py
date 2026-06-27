"""Runs the Trip Concierge agent end-to-end on one multi-step goal.

Prints, in order:
  1. The trace of tool calls the AGENT chose (and in what order/arguments).
  2. The final structured result (validated against schema.TripPlanResult).

Usage:
    export GOOGLE_API_KEY=...      # never hardcode this
    python3 run_agent.py                 # normal run, step cap = 5
    python3 run_agent.py --max-steps 1   # deliberately too low, to prove
                                          # the step limit stops cleanly
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid

from google.genai import types
from google.adk.runners import InMemoryRunner
from google.adk.agents.run_config import RunConfig
from google.adk.agents.invocation_context import LlmCallsLimitExceededError

from agent import build_agent
from safety import StepTracker

try:
    from dotenv import load_dotenv
    load_dotenv()  # reads .env in the current directory into os.environ, if present
except ImportError:
    pass  # python-dotenv not installed -> fall back to real shell env vars only

APP_NAME = "trip_concierge"
MAX_LLM_CALLS = 8  # framework-level backstop, separate from our own step counter


def build_goal(origin: str, destination: str, nights: int, budget_eur: float) -> str:
    return (
        f"Plan a {nights}-night trip to {destination}, flying from {origin}, "
        f"for a total budget of EUR {budget_eur:g} covering flights and "
        f"hotel. Give me the total cost and whether it fits the budget."
    )


async def run_once(max_tool_steps: int, goal: str) -> None:
    step_tracker = StepTracker(max_steps=max_tool_steps)
    agent = build_agent(step_tracker)
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)

    user_id, session_id = "ali", str(uuid.uuid4())
    await runner.session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )

    message = types.Content(role="user", parts=[types.Part(text=goal)])

    print(f"GOAL: {goal}")
    print(f"(step cap = {max_tool_steps} tool calls, llm-call backstop = {MAX_LLM_CALLS})\n")
    print("--- Tool-call trace (agent's own choices) ---")

    final_text = None
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message,
            run_config=RunConfig(max_llm_calls=MAX_LLM_CALLS),
        ):
            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                if part.function_call:
                    print(f"  -> CALL   {part.function_call.name}({part.function_call.args})")
                if part.function_response:
                    print(f"  <- RESULT {part.function_response.name}: {part.function_response.response}")
            if event.is_final_response() and event.content.parts:
                text_parts = [p.text for p in event.content.parts if p.text]
                if text_parts:
                    final_text = "".join(text_parts)
    except LlmCallsLimitExceededError as exc:
        print(f"\n[STOPPED] LLM-call backstop hit before a final answer: {exc}")

    print(f"\nTool calls made: {step_tracker.count} (cap was {step_tracker.max_steps})")
    print("Calls, in order:", step_tracker.calls)

    print("\n--- Final structured result ---")
    if final_text:
        try:
            print(json.dumps(json.loads(final_text), indent=2))
        except json.JSONDecodeError:
            print(final_text)
    else:
        # Graceful fallback: cut off by a limit before a schema-valid final
        # answer was produced. This is the reliability story, demonstrated.
        print(json.dumps({
            "status": "incomplete",
            "notes": "Run stopped by a step/LLM-call limit before a final "
                     "structured answer was produced.",
            "tool_calls_made": step_tracker.count,
        }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-steps", type=int, default=5)
    parser.add_argument("--origin", default="Madrid")
    parser.add_argument("--destination", default="Porto")
    parser.add_argument("--nights", type=int, default=3)
    parser.add_argument("--budget", type=float, default=600.0)
    args = parser.parse_args()

    if not os.environ.get("GOOGLE_API_KEY"):
        raise SystemExit("Set GOOGLE_API_KEY before running this script.")

    goal = build_goal(args.origin, args.destination, args.nights, args.budget)
    asyncio.run(run_once(args.max_steps, goal))