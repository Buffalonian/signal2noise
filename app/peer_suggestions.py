from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

import httpx

from app.company_directory import ensure_loaded, resolve_ticker
from app.config import settings
from app.schemas import PeerSuggestionHit, PeerSuggestionsResponse
from app.sec_cache import read_sec_cache
from app.sec_client import SECClient

logger = logging.getLogger("signalpath.peers")

ROOT = Path(__file__).resolve().parent.parent
CLUSTERS_PATH = ROOT / "data" / "peer_clusters.json"
MAX_PEERS = 8

_sec_client = SECClient()
PeerSource = Literal["ticker", "sic", "none"]


@lru_cache
def _load_clusters() -> dict:
    if not CLUSTERS_PATH.exists():
        logger.warning("Peer clusters file missing: %s", CLUSTERS_PATH)
        return {"by_ticker": {}, "by_sic": {}}
    return json.loads(CLUSTERS_PATH.read_text(encoding="utf-8"))


def _cluster_entry(by_key: dict, key: str) -> tuple[str, list[str]] | None:
    raw = by_key.get(key)
    if not isinstance(raw, dict):
        return None
    label = str(raw.get("label", "")).strip()
    peers = raw.get("peers")
    if not isinstance(peers, list):
        return None
    tickers = [str(t).strip().upper() for t in peers if str(t).strip()]
    return label, tickers


def _resolve_peer_hits(
    tickers: list[str],
    *,
    exclude: str,
    limit: int = MAX_PEERS,
) -> list[PeerSuggestionHit]:
    seen: set[str] = set()
    hits: list[PeerSuggestionHit] = []
    for ticker in tickers:
        if ticker == exclude or ticker in seen:
            continue
        record = resolve_ticker(ticker)
        if record is None:
            continue
        seen.add(ticker)
        hits.append(
            PeerSuggestionHit(ticker=record.ticker, cik=record.cik, name=record.name)
        )
        if len(hits) >= limit:
            break
    return hits


async def _submissions_for_cik(cik: int) -> dict | None:
    cached = read_sec_cache(cik)
    if cached is not None:
        return cached[0]
    try:
        return await _sec_client.get_submissions_by_cik(cik)
    except httpx.HTTPError as exc:
        logger.warning("Could not fetch SEC submissions for CIK %s: %s", cik, exc)
        return None


async def get_peer_suggestions(ticker: str) -> PeerSuggestionsResponse:
    normalized = ticker.strip().upper()
    await ensure_loaded()
    record = resolve_ticker(normalized)
    if record is None:
        return PeerSuggestionsResponse(
            ticker=normalized,
            source="none",
            cluster_label="",
            peers=[],
        )

    clusters = _load_clusters()
    label = ""
    source: PeerSource = "none"
    candidate_tickers: list[str] = []

    ticker_cluster = _cluster_entry(clusters.get("by_ticker", {}), record.ticker)
    if ticker_cluster:
        label, candidate_tickers = ticker_cluster
        source = "ticker"
    else:
        submissions = await _submissions_for_cik(record.cik)
        sic = ""
        sic_desc = ""
        if submissions:
            sic = str(submissions.get("sic", "")).strip()
            sic_desc = str(submissions.get("sicDescription", "")).strip()
        if sic:
            sic_cluster = _cluster_entry(clusters.get("by_sic", {}), sic)
            if sic_cluster:
                cluster_label, candidate_tickers = sic_cluster
                label = cluster_label
                if sic_desc and sic_desc.lower() not in label.lower():
                    label = f"{sic_desc} · {cluster_label}"
                source = "sic"
            elif sic_desc:
                label = sic_desc
                source = "sic"

    peers = _resolve_peer_hits(candidate_tickers, exclude=record.ticker)
    return PeerSuggestionsResponse(
        ticker=record.ticker,
        cik=record.cik,
        company_name=record.name,
        source=source,
        cluster_label=label,
        peers=peers,
    )
