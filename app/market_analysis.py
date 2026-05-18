from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.schemas import (
    MarketAnalysisBlock,
    MarketCheck,
    StockHistoryPoint,
    StockHistoryResponse,
    TrendLineSeries,
)

MarketRating = Literal["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"]

DISCLAIMER = (
    "NOT FINANCIAL ADVICE. For entertainment and education only. "
    "Mock signals use public price data (Yahoo Finance) and simple technical rules — "
    "not SEC filings, not the SignalPath report, and not professional research. "
    "Do not use for trading or investment decisions."
)


@dataclass(frozen=True)
class _Indicators:
    latest_close: float
    period_change_pct: float
    sma_20: float | None
    sma_50: float | None
    rsi_14: float | None
    price_above_sma20: bool
    price_above_sma50: bool
    sma20_above_sma50: bool
    score: float


def _sma_series(closes: list[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(closes)):
        if i < window - 1:
            out.append(None)
        else:
            chunk = closes[i - window + 1 : i + 1]
            out.append(sum(chunk) / window)
    return out


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(-period, 0):
        delta = closes[i] - closes[i - 1]
        if delta >= 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(delta))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _score_to_rating(score: float) -> MarketRating:
    if score >= 1.25:
        return "STRONG_BUY"
    if score >= 0.35:
        return "BUY"
    if score <= -1.25:
        return "STRONG_SELL"
    if score <= -0.35:
        return "SELL"
    return "HOLD"


def _compute_indicators(history: StockHistoryResponse) -> _Indicators:
    closes = [p.close for p in history.points]
    sma20_series = _sma_series(closes, 20)
    sma50_series = _sma_series(closes, 50)
    sma_20 = sma20_series[-1]
    sma_50 = sma50_series[-1]
    latest = closes[-1]

    score = 0.0
    if sma_20 is not None and latest > sma_20:
        score += 0.45
    elif sma_20 is not None and latest < sma_20:
        score -= 0.45

    if sma_50 is not None and latest > sma_50:
        score += 0.35
    elif sma_50 is not None and latest < sma_50:
        score -= 0.35

    if sma_20 is not None and sma_50 is not None:
        if sma_20 > sma_50:
            score += 0.25
        elif sma_20 < sma_50:
            score -= 0.25

    rsi = _rsi(closes)
    if rsi is not None:
        if rsi >= 70:
            score -= 0.35
        elif rsi <= 30:
            score += 0.35

    if history.change_pct >= 8:
        score += 0.25
    elif history.change_pct <= -8:
        score -= 0.25

    return _Indicators(
        latest_close=latest,
        period_change_pct=history.change_pct,
        sma_20=sma_20,
        sma_50=sma_50,
        rsi_14=rsi,
        price_above_sma20=sma_20 is not None and latest > sma_20,
        price_above_sma50=sma_50 is not None and latest > sma_50,
        sma20_above_sma50=sma_20 is not None and sma_50 is not None and sma_20 > sma_50,
        score=round(score, 3),
    )


def _build_checks(ind: _Indicators) -> list[MarketCheck]:
    checks: list[MarketCheck] = []

    if ind.sma_20 is not None:
        checks.append(
            MarketCheck(
                id="price_vs_sma20",
                claim=f"Latest close {'above' if ind.price_above_sma20 else 'below'} 20-day SMA ({ind.sma_20:.2f})",
                supported=True,
                metric_key="sma_20",
                metric_value=f"{ind.sma_20:.2f}",
            )
        )
    if ind.sma_50 is not None:
        checks.append(
            MarketCheck(
                id="price_vs_sma50",
                claim=f"Latest close {'above' if ind.price_above_sma50 else 'below'} 50-day SMA ({ind.sma_50:.2f})",
                supported=True,
                metric_key="sma_50",
                metric_value=f"{ind.sma_50:.2f}",
            )
        )
    if ind.sma_20 is not None and ind.sma_50 is not None:
        checks.append(
            MarketCheck(
                id="sma_cross",
                claim=f"20-day SMA {'above' if ind.sma20_above_sma50 else 'below'} 50-day SMA",
                supported=True,
                metric_key="sma_cross",
                metric_value="bullish" if ind.sma20_above_sma50 else "bearish",
            )
        )
    if ind.rsi_14 is not None:
        zone = "neutral"
        if ind.rsi_14 >= 70:
            zone = "overbought"
        elif ind.rsi_14 <= 30:
            zone = "oversold"
        checks.append(
            MarketCheck(
                id="rsi_14",
                claim=f"14-day RSI at {ind.rsi_14:.1f} ({zone})",
                supported=True,
                metric_key="rsi_14",
                metric_value=f"{ind.rsi_14:.1f}",
            )
        )
    checks.append(
        MarketCheck(
            id="period_return",
            claim=f"Period return {ind.period_change_pct:+.2f}% over selected range",
            supported=True,
            metric_key="change_pct",
            metric_value=f"{ind.period_change_pct:.2f}",
        )
    )
    return checks


def _build_rationale(ind: _Indicators, rating: MarketRating) -> list[str]:
    lines: list[str] = []
    if ind.sma_20 is not None:
        lines.append(
            f"Price is {'above' if ind.price_above_sma20 else 'below'} the 20-day trend line (SMA)."
        )
    if ind.sma_50 is not None:
        lines.append(
            f"Price is {'above' if ind.price_above_sma50 else 'below'} the 50-day trend line (SMA)."
        )
    if ind.sma_20 is not None and ind.sma_50 is not None:
        lines.append(
            "Short-term trend is "
            + ("above" if ind.sma20_above_sma50 else "below")
            + " the longer-term trend (20 vs 50 SMA)."
        )
    if ind.rsi_14 is not None:
        if ind.rsi_14 >= 70:
            lines.append(f"RSI ({ind.rsi_14:.0f}) suggests stretched/overbought conditions.")
        elif ind.rsi_14 <= 30:
            lines.append(f"RSI ({ind.rsi_14:.0f}) suggests washed-out/oversold conditions.")
        else:
            lines.append(f"RSI ({ind.rsi_14:.0f}) is in a neutral zone.")
    lines.append(f"Mock entertainment label: {rating.replace('_', ' ')} (rule score {ind.score:+.2f}).")
    return lines


def build_trend_lines(history: StockHistoryResponse) -> list[TrendLineSeries]:
    closes = [p.close for p in history.points]
    dates = [p.date for p in history.points]
    lines: list[TrendLineSeries] = []

    for window, label in ((20, "SMA 20"), (50, "SMA 50")):
        series = _sma_series(closes, window)
        points: list[StockHistoryPoint] = []
        for date, val in zip(dates, series):
            if val is not None:
                points.append(StockHistoryPoint(date=date, close=round(val, 4)))
        if points:
            lines.append(TrendLineSeries(label=label, points=points))
    return lines


def analyze_market(history: StockHistoryResponse) -> MarketAnalysisBlock:
    ind = _compute_indicators(history)
    rating = _score_to_rating(ind.score)
    summary = (
        f"External price-only mock view: {rating.replace('_', ' ')} "
        f"(technical score {ind.score:+.2f} on {history.range} data)."
    )
    return MarketAnalysisBlock(
        rating=rating,
        score=ind.score,
        summary=summary,
        rationale=_build_rationale(ind, rating),
        checks=_build_checks(ind),
        indicators={
            "latest_close": ind.latest_close,
            "change_pct": ind.period_change_pct,
            "sma_20": ind.sma_20,
            "sma_50": ind.sma_50,
            "rsi_14": ind.rsi_14,
        },
    )
