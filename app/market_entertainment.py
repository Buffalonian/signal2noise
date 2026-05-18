from __future__ import annotations

from app.market_analysis import DISCLAIMER, analyze_market, build_trend_lines
from app.market_validator import validate_market_analysis
from app.schemas import MarketEntertainmentResponse
from app.stock_quotes import fetch_stock_history


async def build_market_entertainment(
    ticker: str, range_: str = "6mo"
) -> MarketEntertainmentResponse:
    history = await fetch_stock_history(ticker, range_)
    analysis = analyze_market(history)
    validation = validate_market_analysis(analysis)
    trend_lines = build_trend_lines(history)

    return MarketEntertainmentResponse(
        ticker=history.ticker,
        range=history.range,
        disclaimer=DISCLAIMER,
        data_source="Yahoo Finance chart API (public prices only)",
        independent_of_report=True,
        history=history,
        trend_lines=trend_lines,
        analysis=analysis,
        validation=validation,
    )
