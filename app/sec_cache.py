from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings

logger = logging.getLogger("signalpath.cache")

ROOT = Path(__file__).resolve().parent.parent


def _cache_dir() -> Path:
    path = Path(settings.sec_cache_dir)
    if not path.is_absolute():
        path = ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_path(cik: int) -> Path:
    return _cache_dir() / f"CIK{str(cik).zfill(10)}.json"


def read_sec_cache(cik: int) -> tuple[dict, dict] | None:
    if not settings.sec_cache_enabled:
        return None
    path = _cache_path(cik)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(payload["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at > timedelta(
            hours=settings.sec_cache_ttl_hours
        ):
            logger.info("SEC cache expired for CIK %s", cik)
            return None
        logger.info("SEC cache hit for CIK %s (fetched %s)", cik, payload["fetched_at"])
        return payload["submissions"], payload["company_facts"]
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning("Invalid SEC cache for CIK %s: %s", cik, exc)
        return None


def write_sec_cache(cik: int, submissions: dict, company_facts: dict) -> None:
    if not settings.sec_cache_enabled:
        return
    path = _cache_path(cik)
    payload = {
        "cik": cik,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "submissions": submissions,
        "company_facts": company_facts,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("SEC cache written for CIK %s → %s", cik, path)
