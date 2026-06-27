"""Standalone tests for the three tools — no model, no API key, no network.

Run with: python3 test_tools.py
"""

from tools import search_flights, search_hotels, calculate


def test_search_flights_known_route():
    result = search_flights("Madrid", "Porto")
    assert result["status"] == "success", result
    assert len(result["options"]) == 3
    print("search_flights(known route)  ->", result)


def test_search_flights_unknown_route():
    result = search_flights("Tokyo", "Porto")
    assert result["status"] == "error", result
    print("search_flights(unknown route) ->", result)


def test_search_hotels_known_city():
    result = search_hotels("Porto", 3)
    assert result["status"] == "success", result
    assert result["nights"] == 3
    print("search_hotels(known city)    ->", result)


def test_search_hotels_invalid_nights():
    result = search_hotels("Porto", -1)
    assert result["status"] == "error", result
    print("search_hotels(invalid nights) ->", result)


def test_calculate_normal():
    result = calculate("58.0 + 65.0 * 3")
    assert result == {"status": "success", "result": 253.0}, result
    print("calculate(valid expr)        ->", result)


def test_calculate_rejects_injection():
    result = calculate("__import__('os').system('echo pwned')")
    assert result["status"] == "error", result
    print("calculate(malicious expr)    ->", result)


if __name__ == "__main__":
    test_search_flights_known_route()
    test_search_flights_unknown_route()
    test_search_hotels_known_city()
    test_search_hotels_invalid_nights()
    test_calculate_normal()
    test_calculate_rejects_injection()
    print("\nAll tool tests passed.")