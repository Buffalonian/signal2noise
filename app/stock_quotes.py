from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.schemas import StockHistoryPoint, StockHistoryResponse

logger = logging.getLogger("signalpath.stocks")

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
ALLOWED_RANGES = frozenset({"1mo", "3mo", "6mo", "1y", "2y", "5y"})


async def fetch_stock_history(ticker: str, range_: str = "6mo") -> StockHistoryResponse:
    symbol = ticker.strip().upper()
    range_key = range_ if range_ in ALLOWED_RANGES else "6mo"

    params = {"range": range_key, "interval": "1d"}
    headers = {
        "User-Agent": "SignalPathIntel/0.1",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            YAHOO_CHART_URL.format(symbol=symbol),
            params=params,
            headers=headers,
        )
        if response.status_code == 404:
            raise ValueError(f"No market data found for ticker '{symbol}'.")
        response.raise_for_status()
        payload = response.json()

    chart = payload.get("chart", {})
    if chart.get("error"):
        err = chart["error"]
        description = err.get("description") if isinstance(err, dict) else str(err)
        raise ValueError(description or f"No chart data for '{symbol}'.")

    results = chart.get("result") or []
    if not results:
        raise ValueError(f"No chart data for '{symbol}'.")

    block = results[0]
    meta = block.get("meta") or {}
    timestamps = block.get("timestamp") or []
    quote = (block.get("indicators") or {}).get("quote") or [{}]
    closes = (quote[0] if quote else {}).get("close") or []

    points: list[StockHistoryPoint] = []
    for ts, close in zip(timestamps, closes):
        if ts is None or close is None:
            continue
        date = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
        points.append(StockHistoryPoint(date=date, close=float(close)))

    if not points:
        raise ValueError(f"No closing prices returned for '{symbol}'.")

    first_close = points[0].close
    last_close = points[-1].close
    change = last_close - first_close
    change_pct = (change / first_close * 100.0) if first_close else 0.0

    currency = str(meta.get("currency") or "USD")
    exchange = str(meta.get("exchangeName") or meta.get("fullExchangeName") or "")

    return StockHistoryResponse(
        ticker=symbol,
        range=range_key,
        currency=currency,
        exchange=exchange,
        points=points,
        latest_close=last_close,
        change=round(change, 4),
        change_pct=round(change_pct, 2),
    )
