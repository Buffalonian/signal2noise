from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from app.graph import compiled_graph
from app.llm_factory import resolved_llm_provider
from app.schemas import CompanySignalRequest, EvidenceItem
from app.session_store import persist_from_graph_state

logger = logging.getLogger("signalpath.run")

NODE_META: dict[str, tuple[int, str]] = {
    "resolve_cik": (1, "Resolve ticker → SEC CIK"),
    "fetch_sec_data": (2, "Fetch SEC submissions & company facts"),
    "extract_evidence": (3, "Extract financial evidence"),
    "generate_report": (4, "Generate signal vs noise report (LLM)"),
    "evaluate_report": (5, "Run evidence audit (LLM)"),
    "finalize_response": (6, "Finalize response"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def build_initial_state(body: CompanySignalRequest) -> dict[str, Any]:
    return {
        "ticker": body.ticker.strip().upper(),
        "company_name": body.company_name.strip(),
        "lens": body.lens.strip(),
        "competitors": [c.strip().upper() for c in body.competitors if c.strip()],
        "errors": [],
    }


def _log_lines(node: str, update: dict[str, Any], merged: dict[str, Any]) -> list[str]:
    step, label = NODE_META.get(node, (0, node))
    prefix = f"Step {step}/6" if step else node
    lines: list[str] = []

    if node == "resolve_cik":
        if update.get("cik"):
            lines.append(f"  → {merged.get('ticker')} mapped to CIK {update['cik']}")
    elif node == "fetch_sec_data":
        if merged.get("sec_from_cache"):
            lines.append("  → SEC data loaded from local cache (no internet fetch)")
        elif update.get("submissions"):
            name = (update["submissions"] or {}).get("name", "unknown")
            lines.append(f"  → Submissions loaded from EDGAR ({name})")
        if update.get("company_facts") and not merged.get("sec_from_cache"):
            lines.append("  → XBRL company facts loaded from EDGAR")
    elif node == "extract_evidence":
        count = len(update.get("evidence") or [])
        lines.append(f"  → {count} evidence item(s) extracted")
    elif node == "generate_report":
        report = update.get("report")
        if report:
            lines.append(
                f"  → Report ready: {len(report.top_signals)} signal(s), "
                f"{len(report.noise)} noise item(s), {len(report.risks)} risk(s)"
            )
    elif node == "evaluate_report":
        evals = update.get("evals")
        if evals:
            lines.append(
                f"  → Audit: passed={evals.passed} score={evals.claim_support_score:.2f}"
            )
    elif node == "finalize_response":
        lines.append("  → Response packaged for UI")

    if update.get("errors"):
        for err in update["errors"]:
            lines.append(f"  ✗ {err}")
        lines.insert(0, f"{prefix} {label} — failed")
    else:
        lines.insert(0, f"{prefix} {label} — completed")
    return lines


def _artifact(node: str, update: dict[str, Any], merged: dict[str, Any]) -> dict[str, Any] | None:
    if node == "extract_evidence" and update.get("evidence"):
        items: list[EvidenceItem] = update["evidence"]
        body = [
            {
                "ref": i,
                "source_type": e.source_type,
                "source_name": e.source_name,
                "text": e.text,
            }
            for i, e in enumerate(items)
        ]
        return {
            "id": "evidence",
            "title": f"Evidence bundle ({len(items)} items)",
            "kind": "json",
            "body": json.dumps(body, indent=2),
        }

    if node == "generate_report" and update.get("report"):
        report = update["report"]
        preview = {
            "executive_summary": report.executive_summary,
            "top_signals": [s.model_dump() for s in report.top_signals],
            "noise": report.noise,
            "risks": [r.model_dump() for r in report.risks],
        }
        return {
            "id": "report",
            "title": "Signal report (preview)",
            "kind": "json",
            "body": json.dumps(preview, indent=2),
        }

    if node == "evaluate_report" and update.get("evals"):
        evals = update["evals"]
        return {
            "id": "eval",
            "title": "Evidence audit result",
            "kind": "json",
            "body": json.dumps(evals.model_dump(), indent=2),
        }

    if node == "finalize_response" and merged.get("response"):
        return {
            "id": "response",
            "title": "Final API response",
            "kind": "json",
            "body": json.dumps(merged["response"].model_dump(), indent=2),
        }

    return None


async def stream_company_signal(body: CompanySignalRequest) -> AsyncIterator[str]:
    initial = build_initial_state(body)
    ticker = initial["ticker"]

    yield _sse(
        "run_start",
        {
            "ts": _utc_now(),
            "ticker": ticker,
            "company_name": initial["company_name"],
            "llm_provider": resolved_llm_provider(),
        },
    )
    logger.info("Stream run started — ticker=%s", ticker)

    merged: dict[str, Any] = dict(initial)
    run_log: list[dict[str, str]] = []
    started = time.perf_counter()

    try:
        async for chunk in compiled_graph.astream(initial, stream_mode="updates"):
            for node_name, update in chunk.items():
                merged.update(update)

                for line in _log_lines(node_name, update, merged):
                    logger.info("[%s] %s", ticker, line)
                    ts = _utc_now()
                    level = "error" if line.strip().startswith("✗") else "info"
                    run_log.append({"ts": ts, "level": level, "message": line})
                    yield _sse(
                        "log",
                        {
                            "ts": ts,
                            "level": level,
                            "message": line,
                            "node": node_name,
                        },
                    )

                artifact = _artifact(node_name, update, merged)
                if artifact:
                    yield _sse("artifact", {"ts": _utc_now(), **artifact})

                step_num = NODE_META.get(node_name, (0, ""))[0]
                yield _sse(
                    "step",
                    {
                        "node": node_name,
                        "step": step_num,
                        "total": 6,
                        "status": "error" if update.get("errors") else "done",
                    },
                )

                if update.get("errors"):
                    message = update["errors"][0]
                    yield _sse("error", {"ts": _utc_now(), "message": message})
                    yield _sse("run_end", {"ts": _utc_now(), "status": "failed"})
                    logger.error("Stream run failed — %s", message)
                    return

        response = merged.get("response")
        if response is None:
            yield _sse(
                "error",
                {
                    "ts": _utc_now(),
                    "message": "Workflow finished without a response.",
                },
            )
            yield _sse("run_end", {"ts": _utc_now(), "status": "failed"})
            return

        elapsed = time.perf_counter() - started
        session_id = persist_from_graph_state(
            request=body,
            merged=merged,
            elapsed_seconds=elapsed,
            run_log=run_log,
        )
        if session_id:
            response.session_id = session_id
            yield _sse(
                "session_saved",
                {"ts": _utc_now(), "session_id": session_id},
            )

        yield _sse(
            "complete",
            {
                "ts": _utc_now(),
                "response": response.model_dump(),
                "session_id": session_id,
            },
        )
        yield _sse("run_end", {"ts": _utc_now(), "status": "succeeded"})
        logger.info("Stream run succeeded — ticker=%s session=%s", ticker, session_id)

    except Exception as exc:
        logger.exception("Stream run unexpected error — ticker=%s", ticker)
        yield _sse(
            "error",
            {"ts": _utc_now(), "message": f"Unexpected error: {exc.__class__.__name__}"},
        )
        yield _sse("run_end", {"ts": _utc_now(), "status": "failed"})
