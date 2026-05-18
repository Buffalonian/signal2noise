from app.market_analysis import analyze_market, build_trend_lines
from app.market_validator import validate_market_analysis
from app.schemas import StockHistoryPoint, StockHistoryResponse


def _history(closes: list[float]) -> StockHistoryResponse:
    points = [
        StockHistoryPoint(date=f"2025-01-{i+1:02d}", close=c) for i, c in enumerate(closes)
    ]
    first, last = closes[0], closes[-1]
    change = last - first
    change_pct = (change / first) * 100 if first else 0.0
    return StockHistoryResponse(
        ticker="TEST",
        range="3mo",
        points=points,
        latest_close=last,
        change=change,
        change_pct=change_pct,
    )


def test_uptrend_maps_to_bullish_rating():
    closes = [100 + i * 1.5 for i in range(60)]
    analysis = analyze_market(_history(closes))
    assert analysis.rating in ("BUY", "STRONG_BUY", "HOLD")
    validation = validate_market_analysis(analysis)
    assert validation.consistency_score > 0.5


def test_trend_lines_include_sma():
    closes = [100 + i * 0.5 for i in range(60)]
    history = _history(closes)
    lines = build_trend_lines(history)
    labels = {line.label for line in lines}
    assert "SMA 20" in labels
    assert "SMA 50" in labels
