from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger("signalpath.directory")

ROOT = Path(__file__).resolve().parent.parent
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

_load_lock = asyncio.Lock()
_records: list[CompanyRecord] | None = None
_by_ticker: dict[str, CompanyRecord] | None = None


@dataclass(frozen=True)
class CompanyRecord:
    ticker: str
    cik: int
    name: str
    name_norm: str


def _cache_path() -> Path:
    path = Path(settings.company_tickers_cache_path)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _normalize_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", name.lower())
    return " ".join(cleaned.split())


def _parse_sec_payload(raw: dict) -> list[CompanyRecord]:
    records: list[CompanyRecord] = []
    for entry in raw.values():
        if not isinstance(entry, dict):
            continue
        ticker = str(entry.get("ticker", "")).strip().upper()
        cik_raw = entry.get("cik_str", entry.get("cik"))
        title = str(entry.get("title", "")).strip()
        if not ticker or cik_raw is None or not title:
            continue
        name = title
        records.append(
            CompanyRecord(
                ticker=ticker,
                cik=int(cik_raw),
                name=name,
                name_norm=_normalize_name(name),
            )
        )
    records.sort(key=lambda r: (r.ticker, r.name))
    return records


def _read_disk_cache() -> list[CompanyRecord] | None:
    path = _cache_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(payload["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at > timedelta(
            hours=settings.company_tickers_ttl_hours
        ):
            logger.info("Company directory cache expired")
            return None
        return [
            CompanyRecord(
                ticker=r["ticker"],
                cik=int(r["cik"]),
                name=r["name"],
                name_norm=r["name_norm"],
            )
            for r in payload["records"]
        ]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Invalid company directory cache: %s", exc)
        return None


def _write_disk_cache(records: list[CompanyRecord]) -> None:
    path = _cache_path()
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "records": [
            {
                "ticker": r.ticker,
                "cik": r.cik,
                "name": r.name,
                "name_norm": r.name_norm,
            }
            for r in records
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Company directory cache written (%s companies) → %s", len(records), path)


async def _fetch_from_sec() -> list[CompanyRecord]:
    headers = {
        "User-Agent": settings.sec_user_agent,
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(SEC_TICKERS_URL, headers=headers)
        response.raise_for_status()
        return _parse_sec_payload(response.json())


def _build_ticker_index(records: list[CompanyRecord]) -> dict[str, CompanyRecord]:
    by_ticker: dict[str, CompanyRecord] = {}
    for record in records:
        # SEC file can list duplicate tickers; keep the first (stable sort).
        by_ticker.setdefault(record.ticker, record)
    return by_ticker


async def ensure_loaded() -> None:
    global _records, _by_ticker
    if _records is not None and _by_ticker is not None:
        return
    async with _load_lock:
        if _records is not None and _by_ticker is not None:
            return
        records = _read_disk_cache()
        if records is None:
            try:
                records = await _fetch_from_sec()
                _write_disk_cache(records)
            except httpx.HTTPError as exc:
                logger.exception("Failed to fetch SEC company tickers")
                raise RuntimeError(
                    "Could not load SEC company directory. Check network and SEC User-Agent."
                ) from exc
        _records = records
        _by_ticker = _build_ticker_index(records)
        logger.info("Company directory loaded — %s tickers", len(_by_ticker))


async def preload_directory() -> None:
    try:
        await ensure_loaded()
    except RuntimeError:
        logger.warning("Company directory preload skipped (will retry on first search)")


def resolve_ticker(ticker: str) -> CompanyRecord | None:
    if _by_ticker is None:
        return None
    return _by_ticker.get(ticker.strip().upper())


def _score(record: CompanyRecord, query: str) -> int:
    q = query.strip()
    if " — " in q:
        q = q.split(" — ", 1)[0].strip()
    if not q:
        return 0
    q_upper = q.upper()
    q_norm = _normalize_name(q)

    if record.ticker == q_upper:
        return 100
    if record.ticker.startswith(q_upper):
        return 92 - min(len(record.ticker) - len(q_upper), 10)
    if q_norm and record.name_norm == q_norm:
        return 88
    if q_norm and record.name_norm.startswith(q_norm):
        return 82 - min(len(record.name_norm) - len(q_norm), 15)
    if q_norm and q_norm in record.name_norm:
        return 70 - min(record.name_norm.index(q_norm), 20)
    return 0


def search_companies(query: str, limit: int = 12) -> list[CompanyRecord]:
    if _records is None:
        return []
    q = query.strip()
    if len(q) < 1:
        return []
    limit = max(1, min(limit, 50))

    scored: list[tuple[int, CompanyRecord]] = []
    seen: set[str] = set()
    for record in _records:
        score = _score(record, q)
        if score <= 0:
            continue
        if record.ticker in seen:
            continue
        seen.add(record.ticker)
        scored.append((score, record))

    scored.sort(key=lambda row: (-row[0], row[1].ticker, row[1].name))
    return [record for _, record in scored[:limit]]
