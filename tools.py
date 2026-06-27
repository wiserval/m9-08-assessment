"""Mock flight/hotel search tools, plus the calculate tool, for the Trip
Concierge agent.

search_flights and search_hotels each return MULTIPLE priced options on
purpose. That's what forces real comparison/decision-making instead of a
single fixed path: the agent has to look at several prices, pick a flight +
hotel combination that fits the budget, and only then call calculate — it
isn't free to just chain three calls in one predetermined order regardless
of what the goal asks for.
"""

from __future__ import annotations

from safety import safe_calculate

_FLIGHTS = {
    ("madrid", "porto"): [
        {"airline": "TAP Air Portugal", "price_eur": 95.0, "departure": "08:10"},
        {"airline": "Ryanair", "price_eur": 58.0, "departure": "21:40"},
        {"airline": "Iberia", "price_eur": 140.0, "departure": "13:25"},
    ],
    ("london", "porto"): [
        {"airline": "easyJet", "price_eur": 72.0, "departure": "07:05"},
        {"airline": "TAP Air Portugal", "price_eur": 110.0, "departure": "16:50"},
    ],
    ("berlin", "porto"): [
        {"airline": "Ryanair", "price_eur": 64.0, "departure": "06:30"},
        {"airline": "Lufthansa", "price_eur": 188.0, "departure": "11:15"},
    ],
}

_HOTELS = {
    "porto": [
        {"name": "Hostel Pao de Acucar", "price_per_night_eur": 28.0, "rating": 4.2},
        {"name": "Hotel Aliados", "price_per_night_eur": 65.0, "rating": 4.5},
        {"name": "Pestana Porto Ribeira", "price_per_night_eur": 145.0, "rating": 4.8},
    ],
}


def search_flights(origin: str, destination: str) -> dict:
    """Searches for round-trip flight options between two cities.

    Args:
        origin: The departure city, e.g. "Madrid".
        destination: The arrival city, e.g. "Porto".

    Returns:
        {"status": "success", "options": [{"airline", "price_eur",
        "departure"}, ...]} or {"status": "error", "error_message": ...}
        if no route is found in the mock dataset.
    """
    key = (str(origin).strip().lower(), str(destination).strip().lower())
    options = _FLIGHTS.get(key)
    if not options:
        return {
            "status": "error",
            "error_message": f"No mock flight data for route {origin} -> {destination}.",
        }
    return {"status": "success", "options": options}


def search_hotels(destination: str, nights: int) -> dict:
    """Searches for hotel options in a city for a given number of nights.

    Args:
        destination: The city to search hotels in, e.g. "Porto".
        nights: Number of nights to stay. Must be a positive integer.

    Returns:
        {"status": "success", "options": [{"name", "price_per_night_eur",
        "rating"}, ...], "nights": <int>} or {"status": "error",
        "error_message": ...} if nights is invalid or the city isn't in the
        mock dataset.
    """
    try:
        nights_int = int(nights)
    except (TypeError, ValueError):
        nights_int = -1
    if nights_int <= 0:
        return {
            "status": "error",
            "error_message": f"'nights' must be a positive integer, got {nights!r}.",
        }
    options = _HOTELS.get(str(destination).strip().lower())
    if not options:
        return {
            "status": "error",
            "error_message": f"No mock hotel data for destination {destination}.",
        }
    return {"status": "success", "options": options, "nights": nights_int}


def calculate(expression: str) -> dict:
    """Safely evaluates a numeric arithmetic expression.

    Only numbers, +, -, *, /, and parentheses are allowed — this is the
    agent's only arithmetic tool, and it is backed by an AST whitelist
    evaluator, never raw eval(). See safety.safe_calculate.

    Args:
        expression: e.g. "58.0 + 65.0 * 3".

    Returns:
        {"status": "success", "result": <float>} or
        {"status": "error", "error_message": ...} if the expression isn't
        valid arithmetic.
    """
    try:
        return {"status": "success", "result": safe_calculate(expression)}
    except ValueError as exc:
        return {"status": "error", "error_message": str(exc)}