"""Fixture report + eval when no OpenAI API key is configured."""

from __future__ import annotations

from app.schemas import (
    EvalResult,
    EvidenceItem,
    EvidenceTableRow,
    SignalItem,
    SignalReport,
)


def build_demo_report(
    ticker: str,
    company_name: str,
    lens: str,
    evidence: list[EvidenceItem],
) -> SignalReport:
    refs = list(range(min(3, len(evidence))))
    primary_ref = refs[0] if refs else []

    summary_bits = [item.text[:120] for item in evidence[:2]]
    evidence_hint = " ".join(summary_bits) if summary_bits else "limited SEC metadata"

    return SignalReport(
        executive_summary=(
            f"Demo report for {company_name} ({ticker}). This run used public SEC evidence only "
            f"and did not call OpenAI. Lens: {lens}. "
            f"Grounding sample: {evidence_hint}…"
        ),
        top_signals=[
            SignalItem(
                claim="Latest SEC XBRL facts provide a baseline on scale and cost structure.",
                why_it_matters=(
                    "Useful for enterprise CI when comparing operating profile against your lens."
                ),
                evidence_refs=primary_ref,
                confidence="medium",
            ),
        ],
        noise=[
            "Generic boilerplate risk language (not evaluated without filing text in demo mode).",
            "Headline-driven narratives not present in the evidence bundle.",
        ],
        risks=[
            SignalItem(
                claim="Financial fact coverage may be incomplete for the selected filing periods.",
                why_it_matters="Weak evidence increases false precision risk in strategic conclusions.",
                evidence_refs=refs,
                confidence="low",
            ),
        ],
        recommended_actions=[
            "Add an OpenAI API key to generate a full LLM-grounded report.",
            "Extend evidence with 10-K Item 1 / 1A / 7 text in a future iteration.",
        ],
        evidence_table=[
            EvidenceTableRow(
                claim=f"SEC evidence [{index}] supports factual grounding only.",
                evidence=item.text[:200],
                source=f"{item.source_type} / {item.source_name}",
                confidence="medium",
            )
            for index, item in enumerate(evidence[:5])
        ],
    )


def build_demo_eval() -> EvalResult:
    return EvalResult(
        passed=True,
        claim_support_score=0.85,
        unsupported_claims=[],
        warnings=[
            "Demo mode: no OpenAI API key configured. Report and audit are illustrative fixtures.",
        ],
    )
