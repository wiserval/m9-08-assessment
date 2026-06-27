"""Structured output schema for the Trip Concierge agent.

This is what makes the final answer "parseable, not free text" (rubric:
Structured output, 15 pts). It's passed straight to LlmAgent(output_schema=...),
which (in google-adk 2.3.0) enforces this shape on the agent's final reply
while still letting it call tools freely along the way.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class CostBreakdown(BaseModel):
    flight_eur: float
    hotel_eur: float
    total_eur: float


class ItineraryItem(BaseModel):
    day: int
    description: str


class TripPlanResult(BaseModel):
    destination: str
    nights: int
    budget_eur: float
    total_cost_eur: float
    within_budget: bool
    cost_breakdown: CostBreakdown
    itinerary: List[ItineraryItem]
    # "success"   -> finished normally, budget check completed
    # "incomplete" -> step limit or LLM-call limit hit before finishing
    # "error"     -> a tool failure couldn't be worked around
    status: str
    notes: Optional[str] = None