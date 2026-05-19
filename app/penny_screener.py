from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.schemas import PennyStockRow, PennyStocksResponse

logger = logging.getLogger("signalpath.penny_screener")

_cache: PennyStocksResponse | None = None
_cache_at: float = 0.0

YAHOO_DISCLAIMER = (
    "Unofficial Yahoo Finance screener data for exploration only — not investment advice "
    "and not part of the SEC signal report."
)
ALPHA_DISCLAIMER = (
    "Alpha Vantage market data (TOP_GAINERS_LOSERS, filtered to penny criteria) — "
    "not investment advice and not part of the SEC signal report."
)


def _resolved_provider() -> str:
    choice = settings.penny_screener_provider
    if choice == "auto":
        if settings.alpha_vantage_api_key.strip():
            return "alpha_vantage"
        return "yahoo"
    return choice


def _build_yahoo_query():
    from yfinance import EquityQuery

    return EquityQuery(
        "and",
        [
            EquityQuery("eq", ["region", "us"]),
            EquityQuery("lte", ["intradayprice", 5]),
            EquityQuery("gte", ["percentchange", 3]),
            EquityQuery("gt", ["dayvolume", 1_000_000]),
        ],
    )


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _quote_to_row(quote: dict[str, Any]) -> PennyStockRow | None:
    symbol = str(quote.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    name = str(quote.get("shortName") or quote.get("longName") or quote.get("name") or symbol)
    return PennyStockRow(
        symbol=symbol,
        name=name,
        price=_num(quote.get("regularMarketPrice") or quote.get("price")),
        change=_num(quote.get("regularMarketChange") or quote.get("change")),
        change_pct=_num(quote.get("regularMarketChangePercent") or quote.get("change_pct")),
        volume=_int(quote.get("regularMarketVolume") or quote.get("volume")),
        market_cap=_num(quote.get("marketCap") or quote.get("market_cap")),
    )


def _fetch_yahoo_penny_stocks(limit: int) -> PennyStocksResponse:
    import yfinance as yf

    started = time.perf_counter()
    result = yf.screen(
        _build_yahoo_query(),
        size=limit,
        sortField="dayvolume",
        sortAsc=False,
    )
    quotes = result.get("quotes", []) if isinstance(result, dict) else []
    stocks: list[PennyStockRow] = []
    for quote in quotes:
        if not isinstance(quote, dict):
            continue
        row = _quote_to_row(quote)
        if row is not None:
            stocks.append(row)
        if len(stocks) >= limit:
            break

    logger.info("Yahoo penny screener returned %s rows in %.1fs", len(stocks), time.perf_counter() - started)
    return PennyStocksResponse(
        stocks=stocks,
        source="yahoo_finance",
        disclaimer=YAHOO_DISCLAIMER,
        updated_at=datetime.now(timezone.utc).isoformat(),
        filters={
            "region": "us",
            "max_price": 5,
            "min_change_pct": 3,
            "min_volume": 1_000_000,
            "sort": "dayvolume_desc",
        },
    )


async def _fetch_alpha_penny_stocks(limit: int) -> PennyStocksResponse:
    from app.alpha_vantage import fetch_top_gainers_losers, penny_rows_from_alpha_vantage

    started = time.perf_counter()
    payload = await fetch_top_gainers_losers()
    raw_rows = penny_rows_from_alpha_vantage(payload, limit=limit)
    stocks: list[PennyStockRow] = []
    for raw in raw_rows:
        row = _quote_to_row(raw)
        if row is not None:
            stocks.append(row)

    last_updated = str(payload.get("last_updated") or "")
    logger.info(
        "Alpha Vantage penny screener returned %s rows in %.1fs",
        len(stocks),
        time.perf_counter() - started,
    )
    return PennyStocksResponse(
        stocks=stocks,
        source="alpha_vantage",
        disclaimer=ALPHA_DISCLAIMER,
        updated_at=datetime.now(timezone.utc).isoformat(),
        filters={
            "endpoint": "TOP_GAINERS_LOSERS",
            "max_price": 5,
            "min_change_pct": 3,
            "min_volume": 1_000_000,
            "sort": "volume_desc",
            "alpha_last_updated": last_updated,
        },
    )


async def fetch_penny_stocks(limit: int = 10) -> PennyStocksResponse:
    """Top US penny stocks — Alpha Vantage when configured, else Yahoo via yfinance."""
    global _cache, _cache_at

    limit = max(1, min(limit, 25))
    ttl_seconds = settings.penny_screener_cache_ttl_minutes * 60
    now = time.time()
    if _cache is not None and (now - _cache_at) < ttl_seconds:
        return _cache.model_copy(update={"stocks": _cache.stocks[:limit]})

    provider = _resolved_provider()
    if provider == "alpha_vantage":
        try:
            response = await _fetch_alpha_penny_stocks(limit)
        except RuntimeError:
            logger.warning("Alpha Vantage screener failed; falling back to Yahoo")
            response = await asyncio.to_thread(_fetch_yahoo_penny_stocks, limit)
            response = response.model_copy(
                update={
                    "disclaimer": response.disclaimer
                    + " (Alpha Vantage unavailable; showing Yahoo fallback.)"
                }
            )
    else:
        response = await asyncio.to_thread(_fetch_yahoo_penny_stocks, limit)

    _cache = response
    _cache_at = now
    return response
