# SignalPath Intel — development log

## 2026-05-18

Session focus: local dev polish, documentation, UI enhancements, and external market-data features (kept separate from the SEC signal report pipeline).

---

### App startup & tooling

- **Fixed import error** blocking `uvicorn`: removed stale `TICKER_CIK_MAP` import from `app/run_stream.py` (ticker resolution now lives in `app/company_directory.py`).
- **Shell alias** added to `~/.zshrc`: `spi` — cds to the project, activates `.venv`, runs `uvicorn app.main:app --reload` on port 8000.
- **`CLAUDE.md` rewritten** to match the real stack and layout (LangGraph, Ollama, company directory, sessions, SEC cache, Vercel entry, API routes, repo status).

---

### Web UI

- **Footer banner** at bottom of app: `SPI © {year}` (year set via JS on load).
- **Peer suggestions** when a company is selected:
  - Curated clusters in `data/peer_clusters.json` (`by_ticker`, `by_sic`).
  - Fallback: SEC SIC from submissions (cache or lightweight fetch).
  - API: `GET /api/companies/{ticker}/peer-suggestions`.
  - UI: clickable chips under Competitors + “Use all”.
- **Stock price chart** for the selected company:
  - Backend: `app/stock_quotes.py` (Yahoo Finance chart API via httpx).
  - API: `GET /api/companies/{ticker}/stock-history?range=…`.
  - UI: canvas chart, 1M / 6M / 1Y / 2Y range tabs, latest price + period change.
- **Market entertainment block** (external only — not the signal report):
  - Mock ratings: `STRONG_BUY`, `BUY`, `HOLD`, `SELL`, `STRONG_SELL` from simple technical rules (SMA 20/50, RSI 14, period return).
  - Trend lines: SMA 20 and SMA 50 overlaid on the price chart.
  - Disclaimer: not financial advice; entertainment / education only.
  - **Separate validation**: `app/market_validator.py` audits rating vs price indicators (independent of `EvalChain` / SEC report).
  - API: `GET /api/companies/{ticker}/market-entertainment?range=…`.
  - UI: disclaimer, rating badge, audit badge, rationale list, integrated chart load.

---

### New / updated backend modules

| File | Purpose |
|------|---------|
| `app/company_directory.py` | (existing) SEC ticker list — used for peer validation |
| `app/peer_suggestions.py` | Peer cluster resolution |
| `app/stock_quotes.py` | Yahoo price history |
| `app/market_analysis.py` | Technical mock rating + SMA series |
| `app/market_validator.py` | Rule-based consistency audit |
| `app/market_entertainment.py` | Orchestrates history + analysis + validation |
| `data/peer_clusters.json` | Curated peer groups + SIC buckets |

---

### API additions (summary)

- `GET /api/companies/{ticker}/peer-suggestions`
- `GET /api/companies/{ticker}/stock-history?range=6mo`
- `GET /api/companies/{ticker}/market-entertainment?range=6mo`

---

### Tests

- `tests/test_peer_suggestions.py` — cluster parsing / peer resolution
- `tests/test_market_analysis.py` — uptrend rating + SMA trend lines

---

### Design decisions (for later)

1. **Report vs market are separate pipelines** — SEC LangGraph report must not drive buy/sell/hold; market view uses public prices only.
2. **Peer lists** are curated + SIC fallback; can extend `data/peer_clusters.json` or add paid comps data later.
3. **Market validation** is rule-based today; optional future: LLM judge on price JSON only (still no report input).
4. **Yahoo Finance** is an unofficial data source — fine for local MVP; production may need a licensed feed.

---

### How to run

```bash
spi
# or
cd ~/projects/signal2noise && source .venv/bin/activate && uvicorn app.main:app --reload
```

Open http://localhost:8000 — select a ticker to see peer chips, price chart, and mock market rating.

---

### Not done today (unchanged / legacy)

- Remove legacy `app/scorer.py`, `static/`, `tests/test_scorer.py`
- 10-K text retrieval, OpenEvals in `EvalChain`, competitor branch in LangGraph
- Production persistence for sessions/cache on Vercel serverless
