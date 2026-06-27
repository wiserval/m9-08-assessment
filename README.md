# Trip Concierge Agent

## Scenario & tools

**Scenario:** Trip concierge. Goal: *"Plan a 3-night trip to Porto, flying
from Madrid, for a total budget of EUR 600 covering flights and hotel."*

**Tools:** `search_flights`, `search_hotels`, `calculate`.

Why this scenario: `search_flights` and `search_hotels` each return
*multiple* priced options instead of one, so the agent has to compare
prices across both tools and choose a flight + hotel combination before it
can call `calculate` — nothing in the code picks an order or a winner for
it. In testing, the agent consistently chose the cheapest available
combination across different budgets, which is a reasonable strategy (it
always satisfies the budget) but didn't produce a captured run where a
binding constraint forced it to reject an option — that would need a
budget below even the cheapest combination's cost, which we didn't test
live (see "Captured run" for what we did capture). The clearer evidence of
real agent reasoning instead came from how it handled a tool failure: see
the reliability note below.

**Built with:** Google ADK (`google-adk==2.3.0`), model `gemini-2.5-flash`.

## Reliability note

Three mechanisms protect the run:

1. **Step limit (primary):** `StepTracker` in `safety.py`, wired in as
   `before_tool_callback`. It counts *work*-tool calls (`search_flights`,
   `search_hotels`, `calculate`) and, once the cap is hit, intercepts the
   next work-tool call before it executes and returns
   `{"status": "step_limit_reached", ...}` instead of running it.
2. **LLM-call backstop (secondary):** `RunConfig(max_llm_calls=8)` is a
   framework-level hard cap on Gemini calls per run. `run_agent.py` catches
   the resulting `LlmCallsLimitExceededError` so an exhausted backstop is
   reported, not an unhandled crash.
3. **Tool-level failure handling:** each tool returns a structured
   `{"status": "error", ...}` instead of raising for expected failures
   (unknown route, invalid `nights`, unparseable expression).

**A real bug we found and fixed:** the step limit originally also counted
and could block ADK's own `set_model_response` tool — the mechanism the
agent uses to deliver its final schema-validated answer. The first
`--max-steps 1` test showed this happening live: `search_hotels` got
blocked as intended, the model correctly composed a graceful "incomplete"
answer, then `set_model_response` *also* got blocked, so a raw
non-schema-shaped error overwrote the model's well-formed answer — worse
than no step limit at all. Fix: `StepTracker` now exempts ADK's finalizing
tool by name (`FINALIZING_TOOL_NAMES` in `safety.py`) from the cap, so the
agent can always deliver an answer — including an honest failure — even
after the work-tool budget is spent. Re-running the same test afterward
confirms the fix (see "Captured run" below): a clean, schema-valid
`status: "error"` result instead of a broken one.

**What this protects against, specifically:** a model that keeps
re-searching or re-calculating indefinitely if a tool fails (cost runaway),
and — the one we actually hit — a safety mechanism silently destroying the
agent's own correct failure-reporting instead of just bounding its
work.

## Safety note

**Mitigation:** `calculate` is backed by `safety.safe_calculate`, an
AST-whitelist arithmetic evaluator — not `eval()`. It only evaluates
numeric literals combined with `+ - * /` and unary `+/-`; any other AST
node (names, calls, attribute access, imports, strings...) raises
`ValueError` before anything executes.

**Attack it defends against:** prompt injection via tool results. Tool
output (e.g. a hotel listing's `name` field) is untrusted text from the
model's point of view — if that text ever steered the model into asking
`calculate` to evaluate something like
`__import__('os').system(...)`, a naive `eval()`-based calculator would
run it. `safe_calculate` cannot, by construction.

**Demonstrated, not just described** (`test_safety.py`, no model involved):

```
Adversarial input: "__import__('os').system('echo pwned-via-calculate') or 1"

--- BEFORE (raw eval) ---
pwned-via-calculate
eval() executed the payload. Result: 1

--- AFTER (safe_calculate) ---
Rejected as expected: ValueError: Disallowed expression element: BoolOp(...)

--- Sanity check: legitimate arithmetic still works ---
safe_calculate('58.0 + 65.0 * 3') -> 253.0
```

The "BEFORE" branch actually ran a real shell command
(`pwned-via-calculate` printed). "AFTER" rejected the identical input while
ordinary arithmetic still works.

## Captured run

**Main run** — `python3 run_agent.py --budget 200` (model: `gemini-2.5-flash`):

```
GOAL: Plan a 3-night trip to Porto, flying from Madrid, for a total budget of EUR 200 covering flights and hotel. Give me the total cost and whether it fits the budget.
(step cap = 5 tool calls, llm-call backstop = 8)
--- Tool-call trace (agent's own choices) ---
  -> CALL   search_flights({'origin': 'Madrid', 'destination': 'Porto'})
  -> CALL   search_hotels({'destination': 'Porto', 'nights': 3})
  <- RESULT search_flights: {'status': 'success', 'options': [{'airline': 'TAP Air Portugal', 'price_eur': 95.0, 'departure': '08:10'}, {'airline': 'Ryanair', 'price_eur': 58.0, 'departure': '21:40'}, {'airline': 'Iberia', 'price_eur': 140.0, 'departure': '13:25'}]}
  <- RESULT search_hotels: {'status': 'success', 'options': [{'name': 'Hostel Pao de Acucar', 'price_per_night_eur': 28.0, 'rating': 4.2}, {'name': 'Hotel Aliados', 'price_per_night_eur': 65.0, 'rating': 4.5}, {'name': 'Pestana Porto Ribeira', 'price_per_night_eur': 145.0, 'rating': 4.8}], 'nights': 3}
  -> CALL   calculate({'expression': '58 + (28 * 3)'})
  <- RESULT calculate: {'status': 'success', 'result': 142}
  -> CALL   set_model_response({...})
Tool calls made: 3 (cap was 5)
Calls, in order: ['search_flights', 'search_hotels', 'calculate', 'set_model_response']

--- Final structured result ---
{
  "destination": "Porto",
  "nights": 3,
  "budget_eur": 200.0,
  "total_cost_eur": 142.0,
  "within_budget": true,
  "cost_breakdown": {"flight_eur": 58.0, "hotel_eur": 84.0, "total_eur": 142.0},
  "itinerary": [
    {"day": 1, "description": "Fly from Madrid to Porto with Ryanair (58 EUR). Check into Hostel Pao de Acucar."},
    {"day": 2, "description": "Explore Porto."},
    {"day": 3, "description": "Explore Porto."},
    {"day": 4, "description": "Check out of Hostel Pao de Acucar and fly back to Madrid."}
  ],
  "status": "success",
  "notes": "The cheapest combination of flight and hotel was chosen, which fits within the budget."
}
```

**Reliability run** — `python3 run_agent.py --max-steps 1` (after the fix above):

```
GOAL: Plan a 3-night trip to Porto, flying from Madrid, for a total budget of EUR 600 covering flights and hotel. Give me the total cost and whether it fits the budget.
(step cap = 1 tool calls, llm-call backstop = 8)
--- Tool-call trace (agent's own choices) ---
  -> CALL   search_flights({'origin': 'Madrid', 'destination': 'Porto'})
  -> CALL   search_hotels({'destination': 'Porto', 'nights': 3})
  <- RESULT search_flights: {'status': 'success', 'options': [...]}
  <- RESULT search_hotels: {'status': 'step_limit_reached', 'error_message': "Step limit of 1 tool calls reached; not executing 'search_hotels'. ..."}
  -> CALL   search_hotels({'nights': 3, 'destination': 'Porto'})   # agent retried with reordered args
  <- RESULT search_hotels: {'status': 'step_limit_reached', 'error_message': "..."}
  -> CALL   set_model_response({'status': 'error', 'within_budget': False, 'total_cost_eur': 0, 'notes': "Could not retrieve hotel information for Porto. The search_hotels tool returned 'step_limit_reached'.", ...})
Tool calls made: 3 (cap was 1)
Calls, in order: ['search_flights', 'search_hotels', 'search_hotels', 'set_model_response']

--- Final structured result ---
{
  "destination": "Porto",
  "nights": 3,
  "budget_eur": 600.0,
  "total_cost_eur": 0.0,
  "within_budget": false,
  "cost_breakdown": {"flight_eur": 0.0, "hotel_eur": 0.0, "total_eur": 0.0},
  "itinerary": [],
  "status": "error",
  "notes": "Could not retrieve hotel information for Porto. The search_hotels tool returned 'step_limit_reached'."
}
```

The agent retried `search_hotels` once on its own (with reordered keyword
arguments — not something our code does), got blocked again, and then gave
up and reported an honest, schema-valid failure rather than fabricating a
number or looping. The step limit itself stopped it cleanly at exactly 1
work-tool call past the cap before this fix was in place; after the fix,
the agent's own failure report survives instead of being overwritten.

## Running it

```bash
pip install -r requirements.txt
export GOOGLE_API_KEY=your-key-here   # or put it in .env (auto-loaded) — never commit it
python3 test_tools.py                # standalone tool tests, no API needed
python3 test_safety.py               # safety before/after demo, no API needed
python3 run_agent.py                       # full run, default budget/step cap
python3 run_agent.py --max-steps 1         # proves the step limit stops cleanly
python3 run_agent.py --budget 200          # try a different budget
```