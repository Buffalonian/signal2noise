from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.config import settings
from app.demo import build_demo_eval
from app.llm_factory import create_chat_model, use_demo_llm
from app.prompts import EVAL_SYSTEM_PROMPT, EVAL_USER_PROMPT
from app.report_generator import format_evidence_block
from app.schemas import EvalResult, EvidenceItem, SignalReport

# TODO(OpenEvals): Wire formal evaluators here for:
# - claim support
# - hallucination detection
# - numerical consistency
# - structured output validation
# - citation coverage
# The rest of the app should keep depending only on EvalChain.evaluate().


class EvalChain:
    def __init__(self) -> None:
        self._demo = use_demo_llm()
        self._chain = None
        if not self._demo:
            llm = create_chat_model()
            structured = llm.with_structured_output(EvalResult)
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", EVAL_SYSTEM_PROMPT),
                    ("human", EVAL_USER_PROMPT),
                ]
            )
            self._chain = prompt | structured

    async def evaluate(
        self, report: SignalReport, evidence: list[EvidenceItem]
    ) -> EvalResult:
        if self._demo:
            return build_demo_eval()

        try:
            result = await self._chain.ainvoke(  # type: ignore[union-attr]
                {
                    "evidence": format_evidence_block(evidence),
                    "report": report.model_dump_json(indent=2),
                }
            )
        except Exception:
            return EvalResult(
                passed=False,
                claim_support_score=0.0,
                unsupported_claims=["Evidence audit could not be completed."],
                warnings=[
                    "Eval chain failed. If using Ollama, confirm the model is pulled "
                    "and supports structured JSON output."
                ],
            )

        if not isinstance(result, EvalResult):
            return EvalResult(
                passed=False,
                claim_support_score=0.0,
                unsupported_claims=["Evidence audit returned invalid structure."],
                warnings=["Eval chain received malformed evaluator output."],
            )

        threshold = settings.claim_support_threshold
        if result.claim_support_score < threshold:
            result.passed = False
            warning = (
                f"Claim support score {result.claim_support_score:.2f} is below "
                f"threshold {threshold:.2f}."
            )
            if warning not in result.warnings:
                result.warnings.append(warning)

        return result
