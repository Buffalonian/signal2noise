from __future__ import annotations

from app.market_analysis import _score_to_rating
from app.schemas import MarketAnalysisBlock, MarketValidation


def validate_market_analysis(analysis: MarketAnalysisBlock) -> MarketValidation:
    """Rule-based audit: external mock rating must match computed indicators."""
    warnings: list[str] = []
    unsupported: list[str] = []

    expected = _score_to_rating(analysis.score)
    if analysis.rating != expected:
        unsupported.append(
            f"Displayed rating {analysis.rating} does not match rule engine ({expected}) "
            f"for score {analysis.score:+.2f}."
        )

    unsupported_checks = [c.claim for c in analysis.checks if not c.supported]
    unsupported.extend(unsupported_checks)

    indicators = analysis.indicators or {}
    rating = analysis.rating
    sma_20 = indicators.get("sma_20")
    sma_50 = indicators.get("sma_50")
    rsi = indicators.get("rsi_14")
    latest = indicators.get("latest_close")
    change_pct = indicators.get("change_pct")

    if latest is not None and sma_20 is not None and sma_50 is not None:
        above_both = latest > sma_20 and latest > sma_50
        below_both = latest < sma_20 and latest < sma_50
        if rating in ("STRONG_BUY", "BUY") and below_both:
            warnings.append(
                "Bullish mock rating while price is below both 20- and 50-day SMAs."
            )
        if rating in ("STRONG_SELL", "SELL") and above_both:
            warnings.append(
                "Bearish mock rating while price is above both 20- and 50-day SMAs."
            )

    if rsi is not None and rating in ("STRONG_BUY", "BUY") and rsi >= 75:
        warnings.append("Bullish mock rating with RSI in overbought territory (≥75).")
    if rsi is not None and rating in ("STRONG_SELL", "SELL") and rsi <= 25:
        warnings.append("Bearish mock rating with RSI in oversold territory (≤25).")

    if change_pct is not None and rating == "STRONG_BUY" and change_pct < -15:
        warnings.append("STRONG_BUY label despite large negative period return.")
    if change_pct is not None and rating == "STRONG_SELL" and change_pct > 15:
        warnings.append("STRONG_SELL label despite large positive period return.")

    consistency = 1.0
    if unsupported:
        consistency -= 0.45
    if warnings:
        consistency -= 0.15 * min(len(warnings), 3)
    consistency = max(0.0, round(consistency, 2))

    passed = not unsupported and consistency >= 0.7

    if not passed and not warnings and unsupported:
        warnings.append("Mock rating failed consistency checks against price indicators.")

    return MarketValidation(
        passed=passed,
        consistency_score=consistency,
        unsupported_claims=unsupported,
        warnings=warnings,
    )
