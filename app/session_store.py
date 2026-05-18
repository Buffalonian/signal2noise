from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.schemas import (
    CompanySignalRequest,
    CompanySignalResponse,
    EvidenceItem,
    RunSessionDetail,
    RunSessionSummary,
)

logger = logging.getLogger("signalpath.sessions")

ROOT = Path(__file__).resolve().parent.parent


def _sessions_dir() -> Path:
    path = Path(settings.sessions_dir)
    if not path.is_absolute():
        path = ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_path(session_id: str) -> Path:
    return _sessions_dir() / f"{session_id}.json"


def save_run_session(
    *,
    request: CompanySignalRequest,
    response: CompanySignalResponse,
    cik: int | None,
    evidence: list[EvidenceItem],
    sec_from_cache: bool,
    llm_provider: str,
    elapsed_seconds: float,
    run_log: list[dict[str, str]],
) -> str | None:
    if not settings.sessions_enabled:
        return None

    session_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    record = {
        "id": session_id,
        "created_at": created_at,
        "request": request.model_dump(),
        "response": response.model_dump(),
        "cik": cik,
        "evidence": [e.model_dump() for e in evidence],
        "sec_from_cache": sec_from_cache,
        "llm_provider": llm_provider,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "run_log": run_log,
    }
    path = _session_path(session_id)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    logger.info("Session saved %s — %s", session_id, path)
    return session_id


def list_sessions(limit: int = 50) -> list[RunSessionSummary]:
    if not settings.sessions_enabled:
        return []
    directory = _sessions_dir()
    files = sorted(
        directory.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    summaries: list[RunSessionSummary] = []
    for path in files[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            response = data.get("response") or {}
            evals = response.get("evals") or {}
            request = data.get("request") or {}
            summaries.append(
                RunSessionSummary(
                    id=data["id"],
                    created_at=data["created_at"],
                    ticker=request.get("ticker", "?"),
                    company_name=request.get("company_name", ""),
                    lens=request.get("lens", "")[:120],
                    eval_passed=bool(evals.get("passed")),
                    claim_support_score=float(evals.get("claim_support_score", 0)),
                    sec_from_cache=bool(data.get("sec_from_cache")),
                    llm_provider=data.get("llm_provider", ""),
                    elapsed_seconds=float(data.get("elapsed_seconds", 0)),
                )
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Skipping corrupt session file %s: %s", path, exc)
    return summaries


def get_session(session_id: str) -> RunSessionDetail | None:
    if not settings.sessions_enabled:
        return None
    path = _session_path(session_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return RunSessionDetail.model_validate(data)


def persist_from_graph_state(
    *,
    request: CompanySignalRequest,
    merged: dict[str, Any],
    elapsed_seconds: float,
    run_log: list[dict[str, str]],
) -> str | None:
    response = merged.get("response")
    if response is None:
        return None
    evidence = merged.get("evidence") or []
    if evidence and not isinstance(evidence[0], EvidenceItem):
        evidence = [EvidenceItem.model_validate(e) for e in evidence]
    return save_run_session(
        request=request,
        response=response,
        cik=merged.get("cik"),
        evidence=evidence,
        sec_from_cache=bool(merged.get("sec_from_cache")),
        llm_provider=merged.get("llm_provider") or "",
        elapsed_seconds=elapsed_seconds,
        run_log=run_log,
    )
