import pytest

from app.peer_suggestions import _cluster_entry, _resolve_peer_hits


def test_cluster_entry_parses_peers():
    by_ticker = {
        "MSFT": {"label": "Software", "peers": ["CRM", "NOW", "msft"]},
    }
    entry = _cluster_entry(by_ticker, "MSFT")
    assert entry is not None
    label, peers = entry
    assert label == "Software"
    assert peers == ["CRM", "NOW", "MSFT"]


def test_resolve_peer_hits_excludes_self(monkeypatch):
    from app import company_directory

    monkeypatch.setattr(
        company_directory,
        "resolve_ticker",
        lambda t: type(
            "R",
            (),
            {"ticker": t, "cik": 1, "name": f"Co {t}"},
        )(),
    )
    hits = _resolve_peer_hits(["MSFT", "CRM", "NOW"], exclude="MSFT", limit=5)
    assert [h.ticker for h in hits] == ["CRM", "NOW"]
