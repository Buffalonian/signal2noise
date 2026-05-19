from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("signalpath.alpha_vantage")

BASE_URL = "https://www.alphavantage.co/query"
_PCT_RE = re.compile(r"[^0-9.\-]")


def _parse_pct(value: str | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(_PCT_RE.sub("", text))
    except ValueError:
        return None


def _parse_num(value: str | float | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _check_api_errors(payload: dict[str, Any]) -> None:
    if "Note" in payload:
        raise RuntimeError(
            "Alpha Vantage rate limit reached. Try again in a minute or use cached data."
        )
    if "Information" in payload:
        raise RuntimeError(str(payload["Information"]))
    if "Error Message" in payload:
        raise RuntimeError(str(payload["Error Message"]))


async def fetch_top_gainers_losers() -> dict[str, Any]:
    api_key = settings.alpha_vantage_api_key.strip()
    if not api_key:
        raise RuntimeError("Alpha Vantage API key is not configured.")

    params = {
        "function": "TOP_GAINERS_LOSERS",
        "apikey": api_key,
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.get(BASE_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Alpha Vantage response.")
    _check_api_errors(payload)
    return payload


def penny_rows_from_alpha_vantage(
    payload: dict[str, Any],
    *,
    limit: int,
    max_price: float = 5.0,
    min_change_pct: float = 3.0,
    min_volume: int = 1_000_000,
) -> list[dict[str, Any]]:
    """
  Build penny-stock candidates from most_actively_traded + top_gainers.
  Alpha Vantage has no Yahoo-style screener; we filter their US lists.
  """
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for key in ("most_actively_traded", "top_gainers"):
        for item in payload.get(key) or []:
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker") or "").strip().upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            merged.append(item)

    rows: list[dict[str, Any]] = []
    for item in merged:
        price = _parse_num(item.get("price"))
        change_pct = _parse_pct(item.get("change_percentage"))
        volume = _parse_int(item.get("volume"))
        if price is None or price > max_price:
            continue
        if change_pct is None or change_pct < min_change_pct:
            continue
        if volume is None or volume < min_volume:
            continue
        rows.append(
            {
                "symbol": str(item.get("ticker") or "").upper(),
                "name": str(item.get("ticker") or "").upper(),
                "price": price,
                "change": _parse_num(item.get("change_amount")),
                "change_pct": change_pct,
                "volume": volume,
            }
        )

    rows.sort(key=lambda r: r.get("volume") or 0, reverse=True)
    return rows[:limit]
