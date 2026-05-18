from typing import Dict, Optional

from pydantic import BaseModel, Field


class CompanySignalRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    company_name: str = Field(min_length=1, max_length=200)
    lens: str = Field(min_length=3, max_length=2000)
    competitors: list[str] = Field(default_factory=list, max_length=10)


class EvidenceItem(BaseModel):
    source_type: str
    source_name: str
    section: Optional[str] = None
    text: str


class SignalItem(BaseModel):
    claim: str
    why_it_matters: str
    evidence_refs: list[int] = Field(default_factory=list)
    confidence: str


class EvidenceTableRow(BaseModel):
    claim: str
    evidence: str
    source: str
    confidence: str


class SignalReport(BaseModel):
    executive_summary: str
    top_signals: list[SignalItem]
    noise: list[str]
    risks: list[SignalItem]
    recommended_actions: list[str]
    evidence_table: list[EvidenceTableRow]


class EvalResult(BaseModel):
    passed: bool
    claim_support_score: float
    unsupported_claims: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CompanySignalResponse(BaseModel):
    ticker: str
    company_name: str
    lens: str
    report: SignalReport
    evals: EvalResult
    session_id: Optional[str] = None


class RunSessionSummary(BaseModel):
    id: str
    created_at: str
    ticker: str
    company_name: str
    lens: str
    eval_passed: bool
    claim_support_score: float
    sec_from_cache: bool
    llm_provider: str
    elapsed_seconds: float


class RunLogEntry(BaseModel):
    ts: str = ""
    level: str = "info"
    message: str = ""


class CompanySearchHit(BaseModel):
    ticker: str
    cik: int
    name: str


class CompanySearchResponse(BaseModel):
    query: str
    results: list[CompanySearchHit]


class PeerSuggestionHit(BaseModel):
    ticker: str
    cik: int
    name: str


class PeerSuggestionsResponse(BaseModel):
    ticker: str
    cik: Optional[int] = None
    company_name: str = ""
    source: str = "none"
    cluster_label: str = ""
    peers: list[PeerSuggestionHit] = Field(default_factory=list)


class StockHistoryPoint(BaseModel):
    date: str
    close: float


class StockHistoryResponse(BaseModel):
    ticker: str
    range: str
    currency: str = "USD"
    exchange: str = ""
    points: list[StockHistoryPoint]
    latest_close: float
    change: float
    change_pct: float


class TrendLineSeries(BaseModel):
    label: str
    points: list[StockHistoryPoint]


class MarketCheck(BaseModel):
    id: str
    claim: str
    supported: bool = True
    metric_key: str = ""
    metric_value: str = ""


class MarketAnalysisBlock(BaseModel):
    rating: str
    score: float
    summary: str
    rationale: list[str] = Field(default_factory=list)
    checks: list[MarketCheck] = Field(default_factory=list)
    indicators: Dict[str, Optional[float]] = Field(default_factory=dict)


class MarketValidation(BaseModel):
    passed: bool
    consistency_score: float
    unsupported_claims: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MarketEntertainmentResponse(BaseModel):
    ticker: str
    range: str
    disclaimer: str
    data_source: str
    independent_of_report: bool = True
    history: StockHistoryResponse
    trend_lines: list[TrendLineSeries] = Field(default_factory=list)
    analysis: MarketAnalysisBlock
    validation: MarketValidation


class RunSessionDetail(BaseModel):
    id: str
    created_at: str
    request: CompanySignalRequest
    response: CompanySignalResponse
    cik: Optional[int] = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    sec_from_cache: bool = False
    llm_provider: str = ""
    elapsed_seconds: float = 0.0
    run_log: list[RunLogEntry] = Field(default_factory=list)
