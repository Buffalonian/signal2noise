from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.demo import build_demo_report
from app.llm_factory import create_chat_model, use_demo_llm
from app.prompts import REPORT_SYSTEM_PROMPT, REPORT_USER_PROMPT
from app.schemas import EvidenceItem, SignalReport


class ReportGenerationError(Exception):
    """Raised when the model returns output that cannot be parsed into SignalReport."""


def format_evidence_block(evidence: list[EvidenceItem]) -> str:
    lines: list[str] = []
    for index, item in enumerate(evidence):
        section = f" section={item.section}" if item.section else ""
        lines.append(
            f"[{index}] ({item.source_type}) {item.source_name}{section}: {item.text}"
        )
    return "\n".join(lines) if lines else "(no evidence provided)"


class ReportGenerator:
    def __init__(self) -> None:
        self._demo = use_demo_llm()
        self._chain = None
        if not self._demo:
            llm = create_chat_model()
            structured = llm.with_structured_output(SignalReport)
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", REPORT_SYSTEM_PROMPT),
                    ("human", REPORT_USER_PROMPT),
                ]
            )
            self._chain = prompt | structured

    async def generate(
        self,
        ticker: str,
        company_name: str,
        lens: str,
        competitors: list[str],
        evidence: list[EvidenceItem],
    ) -> SignalReport:
        if self._demo:
            return build_demo_report(ticker, company_name, lens, evidence)

        competitors_line = ", ".join(competitors) if competitors else "none specified"
        try:
            result = await self._chain.ainvoke(  # type: ignore[union-attr]
                {
                    "company_name": company_name,
                    "ticker": ticker.upper(),
                    "lens": lens,
                    "competitors": competitors_line,
                    "evidence": format_evidence_block(evidence),
                }
            )
        except Exception as exc:
            raise ReportGenerationError(
                "Failed to generate a structured signal report. "
                "If using Ollama, check that it is running and OLLAMA_MODEL matches "
                "`ollama list`."
            ) from exc

        if not isinstance(result, SignalReport):
            raise ReportGenerationError(
                "Model output could not be parsed into a SignalReport."
            )
        return result
