from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.company_directory import ensure_loaded, preload_directory, search_companies
from app.peer_suggestions import get_peer_suggestions
from app.market_entertainment import build_market_entertainment
from app.stock_quotes import fetch_stock_history
from app.config import settings
from app.graph import compiled_graph
from app.llm_factory import resolved_llm_provider
from app.logging_setup import configure_logging
from app.run_stream import build_initial_state, stream_company_signal
from app.schemas import (
    CompanySearchHit,
    CompanySearchResponse,
    CompanySignalRequest,
    PeerSuggestionsResponse,
    MarketEntertainmentResponse,
    StockHistoryResponse,
    CompanySignalResponse,
    RunSessionDetail,
    RunSessionSummary,
)
from app.session_store import get_session, list_sessions, persist_from_graph_state

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

logger = logging.getLogger("signalpath.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info(
        "SignalPath Intel started — llm_provider=%s ollama_model=%s",
        resolved_llm_provider(),
        settings.ollama_model,
    )
    await preload_directory()
    yield
    logger.info("SignalPath Intel shutting down")


app = FastAPI(title="SignalPath Intel", version="0.1.0", lifespan=lifespan)


def _raise_for_graph_errors(errors: list[str]) -> None:
    if not errors:
        return
    message = errors[0]
    if message.startswith("UNKNOWN_TICKER:"):
        raise HTTPException(status_code=400, detail=message.split(":", 1)[1].strip())
    if message.startswith("SEC_FETCH_FAILED:"):
        raise HTTPException(status_code=502, detail=message.split(":", 1)[1].strip())
    if message.startswith("NO_EVIDENCE:"):
        raise HTTPException(status_code=404, detail=message.split(":", 1)[1].strip())
    if message.startswith("REPORT_GENERATION_FAILED:"):
        raise HTTPException(status_code=500, detail=message.split(":", 1)[1].strip())
    raise HTTPException(status_code=500, detail="Report workflow failed.")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "llm_provider": resolved_llm_provider()}


@app.post("/reports/company-signal", response_model=CompanySignalResponse)
async def company_signal(body: CompanySignalRequest) -> CompanySignalResponse:
    ticker = body.ticker.strip().upper()
    started = time.perf_counter()
    logger.info(
        "POST /reports/company-signal — ticker=%s company=%s lens=%r competitors=%s",
        ticker,
        body.company_name.strip(),
        body.lens.strip()[:80],
        body.competitors,
    )

    initial_state = build_initial_state(body)

    try:
        final_state = await compiled_graph.ainvoke(initial_state)
    except Exception:
        logger.exception("Workflow failed with unexpected error for ticker=%s", ticker)
        raise

    elapsed = time.perf_counter() - started

    if final_state.get("errors"):
        logger.error(
            "Workflow error for %s after %.1fs — %s",
            ticker,
            elapsed,
            final_state["errors"],
        )
        _raise_for_graph_errors(final_state["errors"])

    response = final_state.get("response")
    if response is None:
        logger.error("No response in final state for %s after %.1fs", ticker, elapsed)
        raise HTTPException(
            status_code=500,
            detail="Report workflow completed without a response.",
        )

    session_id = persist_from_graph_state(
        request=body,
        merged=final_state,
        elapsed_seconds=elapsed,
        run_log=[],
    )
    if session_id:
        response.session_id = session_id

    logger.info(
        "POST /reports/company-signal done — ticker=%s elapsed=%.1fs session=%s",
        ticker,
        elapsed,
        session_id,
    )
    return response


@app.get("/api/companies/search", response_model=CompanySearchResponse)
async def companies_search(q: str = "", limit: int = 12) -> CompanySearchResponse:
    query = q.strip()
    if len(query) < 1:
        return CompanySearchResponse(query=query, results=[])
    try:
        await ensure_loaded()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    hits = search_companies(query, limit=min(limit, 50))
    return CompanySearchResponse(
        query=query,
        results=[
            CompanySearchHit(ticker=h.ticker, cik=h.cik, name=h.name) for h in hits
        ],
    )


@app.get("/api/companies/{ticker}/stock-history", response_model=StockHistoryResponse)
async def company_stock_history(
    ticker: str, range: str = "6mo"
) -> StockHistoryResponse:
    try:
        return await fetch_stock_history(ticker, range)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        logger.warning("Stock history fetch failed for %s", ticker, exc_info=exc)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch market data right now.",
        ) from exc


@app.get(
    "/api/companies/{ticker}/market-entertainment",
    response_model=MarketEntertainmentResponse,
)
async def company_market_entertainment(
    ticker: str, range: str = "6mo"
) -> MarketEntertainmentResponse:
    """Mock buy/sell/hold from external prices only — not the SEC signal report."""
    try:
        return await build_market_entertainment(ticker, range)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        logger.warning("Market entertainment fetch failed for %s", ticker, exc_info=exc)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch market data right now.",
        ) from exc


@app.get("/api/companies/{ticker}/peer-suggestions", response_model=PeerSuggestionsResponse)
async def company_peer_suggestions(ticker: str) -> PeerSuggestionsResponse:
    try:
        await ensure_loaded()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return await get_peer_suggestions(ticker)


@app.get("/api/sessions", response_model=list[RunSessionSummary])
def sessions_list(limit: int = 50) -> list[RunSessionSummary]:
    return list_sessions(limit=min(limit, 100))


@app.get("/api/sessions/{session_id}", response_model=RunSessionDetail)
def sessions_get(session_id: str) -> RunSessionDetail:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


@app.post("/reports/company-signal/stream")
async def company_signal_stream(body: CompanySignalRequest) -> StreamingResponse:
    """Server-sent events: real pipeline logs and artifacts as each step completes."""
    logger.info("POST /reports/company-signal/stream — ticker=%s", body.ticker.strip().upper())
    return StreamingResponse(
        stream_company_signal(body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


app.mount("/web", StaticFiles(directory=str(WEB)), name="web")
