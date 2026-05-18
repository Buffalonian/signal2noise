import pytest

from app.company_directory import CompanyRecord, _build_ticker_index, search_companies


@pytest.fixture
def sample_records() -> list[CompanyRecord]:
    records = [
        CompanyRecord("MSFT", 789019, "MICROSOFT CORP", "microsoft corp"),
        CompanyRecord("AAPL", 320193, "Apple Inc.", "apple inc"),
        CompanyRecord("CRM", 1108524, "Salesforce, Inc.", "salesforce inc"),
    ]
    import app.company_directory as directory

    directory._records = records
    directory._by_ticker = _build_ticker_index(records)
    yield records
    directory._records = None
    directory._by_ticker = None


def test_search_ticker_prefix(sample_records):
    hits = search_companies("MSF", limit=5)
    assert hits[0].ticker == "MSFT"


def test_search_company_name(sample_records):
    hits = search_companies("salesforce", limit=5)
    assert any(h.ticker == "CRM" for h in hits)


def test_resolve_ticker(sample_records):
    import app.company_directory as directory

    record = directory.resolve_ticker("aapl")
    assert record is not None
    assert record.cik == 320193
