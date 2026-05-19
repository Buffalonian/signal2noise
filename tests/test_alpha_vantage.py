from app.alpha_vantage import penny_rows_from_alpha_vantage


def test_penny_rows_from_alpha_vantage_filters_and_sorts():
    payload = {
        "most_actively_traded": [
            {
                "ticker": "VRAX",
                "price": "0.235",
                "change_amount": "0.08",
                "change_percentage": "53.0%",
                "volume": "760000000",
            },
            {
                "ticker": "AAPL",
                "price": "200.0",
                "change_amount": "1.0",
                "change_percentage": "1.0%",
                "volume": "50000000",
            },
        ],
        "top_gainers": [],
    }
    rows = penny_rows_from_alpha_vantage(payload, limit=5)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "VRAX"
    assert rows[0]["price"] == 0.235
    assert rows[0]["change_pct"] == 53.0
