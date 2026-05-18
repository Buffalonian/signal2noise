from __future__ import annotations

import logging
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, StateGraph

from app.company_directory import ensure_loaded, resolve_ticker
from app.eval_chain import EvalChain
from app.report_generator import ReportGenerationError, ReportGenerator
from app.schemas import CompanySignalResponse, EvalResult, EvidenceItem, SignalReport
from app.sec_client import (
    SECClient,
    extract_basic_financial_evidence,
    extract_submissions_metadata_evidence,
)

logger = logging.getLogger(__name__)

_sec_client = SECClient()
_report_generator = ReportGenerator()
_eval_chain = EvalChain()


class GraphState(TypedDict, total=False):
    ticker: str
    company_name: str
    lens: str
    competitors: list[str]
    cik: int
    sec_from_cache: bool
    submissions: dict[str, Any]
    company_facts: dict[str, Any]
    evidence: list[EvidenceItem]
    report: SignalReport
    evals: EvalResult
    response: CompanySignalResponse
    errors: list[str]


def _has_errors(state: GraphState) -> bool:
    return bool(state.get("errors"))


async def resolve_cik(state: GraphState) -> dict[str, Any]:
    ticker = state["ticker"].strip().upper()
    logger.info("Step 1/6 resolve_cik — ticker=%s", ticker)
    try:
        await ensure_loaded()
    except RuntimeError as exc:
        return {"errors": [f"UNKNOWN_TICKER: {exc}"]}
    record = resolve_ticker(ticker)
    if record is None:
        logger.warning("Unknown ticker: %s", ticker)
        return {
            "errors": [
                f"UNKNOWN_TICKER: '{ticker}' not found in SEC listings. "
                "Use the company lookup to pick a listed ticker."
            ]
        }
    logger.info("Resolved %s → CIK %s (%s)", record.ticker, record.cik, record.name)
    company_name = state.get("company_name", "").strip() or record.name
    return {
        "cik": record.cik,
        "ticker": record.ticker,
        "company_name": company_name,
        "errors": [],
    }


async def fetch_sec_data(state: GraphState) -> dict[str, Any]:
    cik = state["cik"]
    logger.info("Step 2/6 fetch_sec_data — CIK=%s", cik)
    try:
        submissions, company_facts, from_cache = await _sec_client.fetch_company_data(
            cik
        )
        if from_cache:
            logger.info("SEC data loaded from cache for CIK %s", cik)
        else:
            logger.info("SEC data fetched from EDGAR for CIK %s", cik)
    except httpx.HTTPError as exc:
        logger.warning("SEC fetch failed for CIK %s", cik, exc_info=exc)
        return {
            "errors": [
                f"SEC_FETCH_FAILED: Unable to fetch SEC data for CIK {cik}."
            ]
        }
    return {
        "submissions": submissions,
        "company_facts": company_facts,
        "sec_from_cache": from_cache,
        "errors": [],
    }


async def extract_evidence(state: GraphState) -> dict[str, Any]:
    logger.info("Step 3/6 extract_evidence")
    submissions = state.get("submissions") or {}
    company_facts = state.get("company_facts") or {}

    evidence: list[EvidenceItem] = []
    metadata = extract_submissions_metadata_evidence(submissions)
    if metadata:
        evidence.append(metadata)
    evidence.extend(extract_basic_financial_evidence(company_facts))

    if not evidence:
        logger.warning("No evidence extracted from SEC payloads")
        return {"errors": ["NO_EVIDENCE: No evidence could be extracted from SEC data."]}
    logger.info("Extracted %s evidence item(s)", len(evidence))
    return {"evidence": evidence, "errors": []}


async def generate_report(state: GraphState) -> dict[str, Any]:
    logger.info("Step 4/6 generate_report — calling LLM (may take 1–3 min on Ollama)")
    try:
        report = await _report_generator.generate(
            ticker=state["ticker"],
            company_name=state["company_name"],
            lens=state["lens"],
            competitors=state.get("competitors") or [],
            evidence=state["evidence"],
        )
    except ReportGenerationError as exc:
        logger.error("Report generation failed: %s", exc)
        return {
            "errors": [
                f"REPORT_GENERATION_FAILED: {exc.args[0] if exc.args else str(exc)}"
            ]
        }
    logger.info(
        "Report generated — %s signal(s), %s risk(s)",
        len(report.top_signals),
        len(report.risks),
    )
    return {"report": report, "errors": []}


async def evaluate_report(state: GraphState) -> dict[str, Any]:
    logger.info("Step 5/6 evaluate_report — evidence audit")
    report = state["report"]
    evals = await _eval_chain.evaluate(report, state["evidence"])
    logger.info(
        "Eval complete — passed=%s score=%.2f warnings=%s",
        evals.passed,
        evals.claim_support_score,
        len(evals.warnings),
    )
    return {"evals": evals}


async def finalize_response(state: GraphState) -> dict[str, Any]:
    logger.info("Step 6/6 finalize_response")
    from app.llm_factory import resolved_llm_provider

    response = CompanySignalResponse(
        ticker=state["ticker"],
        company_name=state["company_name"],
        lens=state["lens"],
        report=state["report"],
        evals=state["evals"],
    )
    return {
        "response": response,
        "llm_provider": resolved_llm_provider(),
    }


def _route_on_errors(state: GraphState) -> str:
    return "error" if _has_errors(state) else "continue"


def build_workflow() -> StateGraph:
    workflow: StateGraph = StateGraph(GraphState)

    workflow.add_node("resolve_cik", resolve_cik)
    workflow.add_node("fetch_sec_data", fetch_sec_data)
    workflow.add_node("extract_evidence", extract_evidence)
    workflow.add_node("generate_report", generate_report)
    workflow.add_node("evaluate_report", evaluate_report)
    workflow.add_node("finalize_response", finalize_response)

    workflow.set_entry_point("resolve_cik")

    workflow.add_conditional_edges(
        "resolve_cik",
        _route_on_errors,
        {"error": END, "continue": "fetch_sec_data"},
    )
    workflow.add_conditional_edges(
        "fetch_sec_data",
        _route_on_errors,
        {"error": END, "continue": "extract_evidence"},
    )
    workflow.add_conditional_edges(
        "extract_evidence",
        _route_on_errors,
        {"error": END, "continue": "generate_report"},
    )
    workflow.add_conditional_edges(
        "generate_report",
        _route_on_errors,
        {"error": END, "continue": "evaluate_report"},
    )
    workflow.add_edge("evaluate_report", "finalize_response")
    workflow.add_edge("finalize_response", END)

    return workflow


# TODO: Add LangGraph checkpointing for longer-running reports.
# TODO: Add repair loop if eval fails.
# TODO: Add source citation URLs.
# TODO: Add actual 10-K text retrieval and section parsing.
# TODO: Add competitor comparison graph branch.

compiled_graph = build_workflow().compile()
