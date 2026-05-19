from __future__ import annotations

from unittest.mock import patch

from app.penny_screener import _fetch_yahoo_penny_stocks


def test_fetch_yahoo_penny_stocks_maps_quotes():
    fake_quotes = [
        {
            "symbol": "VRAX",
            "shortName": "Virax Biolabs Group Limited",
            "regularMarketPrice": 0.235,
            "regularMarketChange": 0.09,
            "regularMarketChangePercent": 53.1,
            "regularMarketVolume": 760_215_546,
            "marketCap": 1_822_000,
        }
    ]

    with patch("yfinance.screen", return_value={"quotes": fake_quotes}):
        # Clear module cache between tests
        import app.penny_screener as mod

        mod._cache = None
        mod._cache_at = 0.0
        result = _fetch_yahoo_penny_stocks(limit=1)

    assert len(result.stocks) == 1
    row = result.stocks[0]
    assert row.symbol == "VRAX"
    assert row.name == "Virax Biolabs Group Limited"
    assert row.price == 0.235
    assert row.change_pct == 53.1
    assert row.volume == 760_215_546
