from __future__ import annotations

import httpx

from app.config import settings
from app.schemas import EvidenceItem
from app.sec_cache import read_sec_cache, write_sec_cache

GAAP_FINANCIAL_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "OperatingIncomeLoss",
    "ResearchAndDevelopmentExpense",
    "SellingGeneralAndAdministrativeExpense",
    "NetIncomeLoss",
)


class SECClient:
    def __init__(self) -> None:
        self._base = settings.sec_base_url.rstrip("/")
        self._headers = {
            "User-Agent": settings.sec_user_agent,
            "Accept": "application/json",
        }

    def _cik_padded(self, cik: int) -> str:
        return str(cik).zfill(10)

    async def get_submissions_by_cik(self, cik: int) -> dict:
        url = f"{self._base}/submissions/CIK{self._cik_padded(cik)}.json"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers)
            response.raise_for_status()
            return response.json()

    async def get_company_facts(self, cik: int) -> dict:
        url = f"{self._base}/api/xbrl/companyfacts/CIK{self._cik_padded(cik)}.json"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers)
            response.raise_for_status()
            return response.json()

    async def fetch_company_data(self, cik: int) -> tuple[dict, dict, bool]:
        """Returns (submissions, company_facts, from_cache)."""
        cached = read_sec_cache(cik)
        if cached is not None:
            return cached[0], cached[1], True
        submissions = await self.get_submissions_by_cik(cik)
        company_facts = await self.get_company_facts(cik)
        write_sec_cache(cik, submissions, company_facts)
        return submissions, company_facts, False


def extract_basic_financial_evidence(company_facts: dict) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    us_gaap = company_facts.get("facts", {}).get("us-gaap", {})
    if not isinstance(us_gaap, dict):
        return items

    for tag in GAAP_FINANCIAL_TAGS:
        tag_data = us_gaap.get(tag)
        if not tag_data:
            continue
        units = tag_data.get("units", {})
        if not units:
            continue
        entries = units.get("USD")
        if not entries:
            entries = next(iter(units.values()), [])
        if not entries:
            continue
        latest = max(entries, key=lambda row: row.get("end", ""))
        text = (
            f"{tag}: value={latest.get('val')} "
            f"form={latest.get('form')} fy={latest.get('fy')} "
            f"fp={latest.get('fp')} filed={latest.get('filed')}"
        )
        items.append(
            EvidenceItem(
                source_type="SEC XBRL companyfacts",
                source_name=tag,
                section="financial_fact",
                text=text,
            )
        )
    return items


def extract_submissions_metadata_evidence(submissions: dict) -> EvidenceItem | None:
    name = submissions.get("name")
    sic = submissions.get("sic")
    fiscal_year_end = submissions.get("fiscalYearEnd")
    entity_type = submissions.get("entityType")
    if not any([name, sic, fiscal_year_end, entity_type]):
        return None
    text = (
        f"Company name={name}; SIC={sic}; "
        f"fiscal year end={fiscal_year_end}; entity type={entity_type}"
    )
    return EvidenceItem(
        source_type="SEC EDGAR submissions",
        source_name="entity_metadata",
        section="metadata",
        text=text,
    )
