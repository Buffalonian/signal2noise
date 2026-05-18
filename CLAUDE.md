# SignalPath Intel — project guide for AI assistants

Local MVP: **signalpath-intel** (repo may be named `signal2noise`) — a Python FastAPI app with a plain browser UI that takes a public company ticker and business lens, pulls SEC public data, runs a **LangGraph** pipeline to generate a “signal vs noise” competitive-intelligence report, and runs an LLM-as-judge evidence audit to reduce hallucinations.

**Keep it simple.** No auth, billing, Docker, React build step, or background workers. File-based session history and SEC cache are fine for local dev only.

---

## Stack

| Layer | Choice |
|-------|--------|
| Runtime | Python 3.11 (local venv may be 3.9 — prefer 3.11) |
| API | FastAPI + Pydantic + Pydantic Settings |
| Workflow | LangGraph (`app/graph.py`) — 6-step state machine |
| HTTP (SEC) | httpx (async) |
| Config | `app/config.py` → `Settings` / `settings` from `.env.local` only — **never** scatter `os.getenv()` |
| LLM | LangChain chat models via `app/llm_factory.py` — OpenAI or **Ollama** (`auto` prefers OpenAI when keyed) |
| Evals | LLM-as-judge in `EvalChain`; OpenEvals placeholder — **do not block MVP on OpenEvals** |
| Frontend | Plain HTML / CSS / vanilla JS in `web/` — no build step |
| Deploy | Optional Vercel ASGI via `api/index.py` + `vercel.json` (serverless has no persistent `data/`) |

---

## Layout

```
signal2noise/                 # repo root (product: SignalPath Intel)
  api/index.py                # Vercel: `from app.main import app`
  app/
    main.py                   # FastAPI routes, static mount, lifespan
    config.py                 # Settings from .env.local
    schemas.py                # Pydantic models
    graph.py                  # LangGraph workflow (compiled_graph)
    run_stream.py             # SSE streaming for /reports/company-signal/stream
    company_directory.py      # SEC company_tickers.json → ticker/CIK lookup + search
    sec_client.py             # SEC EDGAR async client
    sec_cache.py              # Per-CIK JSON cache under data/sec_cache/
    report_generator.py       # LLM report generation
    eval_chain.py             # Evidence audit + OpenEvals placeholder
    llm_factory.py            # OpenAI / Ollama / demo provider resolution
    prompts.py                # System/user prompt strings
    session_store.py          # JSON run history under data/sessions/
    logging_setup.py
    demo.py                   # Fixture responses when DEMO_MODE
  web/
    index.html
    app.js
    styles.css
  data/
    company_tickers.json      # Cached SEC ticker list (auto-downloaded)
    sec_cache/                # Per-CIK SEC payloads
    sessions/                 # Saved report runs
  tests/
    test_company_directory.py
  requirements.txt
  runtime.txt
  vercel.json
  .env.local.example
  .gitignore                  # must include .env.local
  README.md
```

**Legacy (do not extend):** `app/scorer.py`, `tests/test_scorer.py`, `static/` — remove when cleaning up.

---

## Configuration (`app/config.py`)

Load from **`.env.local`** only through `Settings` / `settings`.

| Variable | Default | Notes |
|----------|---------|--------|
| `LLM_PROVIDER` | `auto` | `auto` \| `openai` \| `ollama` \| `demo` |
| `OPENAI_API_KEY` | `""` | Optional; `auto` uses OpenAI when set |
| `OPENAI_MODEL` | `gpt-4.1-mini` | |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | |
| `OLLAMA_MODEL` | `qwen3:8b` | Match `ollama list` |
| `DEMO_MODE` | `false` | Fixture-only, no LLM calls |
| `SEC_USER_AGENT` | `SignalPathIntel/0.1 contact@example.com` | Required by SEC |
| `SEC_BASE_URL` | `https://data.sec.gov` | |
| `CLAIM_SUPPORT_THRESHOLD` | `0.75` | Below → `evals.passed=false` |
| `SESSIONS_ENABLED` | `true` | JSON files in `SESSIONS_DIR` |
| `SESSIONS_DIR` | `data/sessions` | |
| `SEC_CACHE_ENABLED` | `true` | Per-CIK cache in `SEC_CACHE_DIR` |
| `SEC_CACHE_DIR` | `data/sec_cache` | |
| `SEC_CACHE_TTL_HOURS` | `24` | |
| `COMPANY_TICKERS_CACHE_PATH` | `data/company_tickers.json` | |
| `COMPANY_TICKERS_TTL_HOURS` | `168` | |

Ship `.env.local.example` with these keys. Add `.env.local` to `.gitignore`.

---

## API

### `POST /reports/company-signal`

Synchronous full pipeline via `compiled_graph.ainvoke`. Persists session when `SESSIONS_ENABLED`.

**Request**

```json
{
  "ticker": "MSFT",
  "company_name": "Microsoft",
  "lens": "AI strategy, cloud growth, cybersecurity risk, margin pressure",
  "competitors": ["CRM", "NOW", "TEAM"]
}
```

**Response** — `CompanySignalResponse`: `ticker`, `company_name`, `lens`, `report` (`SignalReport`), `evals` (`EvalResult`), optional `session_id`.

Graph errors map to HTTP status in `main._raise_for_graph_errors`: `UNKNOWN_TICKER` → 400, `SEC_FETCH_FAILED` → 502, `NO_EVIDENCE` → 404, `REPORT_GENERATION_FAILED` → 500.

### `POST /reports/company-signal/stream`

Server-sent events (`app/run_stream.py`): `run_start`, `log`, `artifact`, `step`, `error`, `complete`, `session_saved`, `run_end`. UI uses this for live pipeline progress.

### `GET /api/companies/search?q=...&limit=12`

Typeahead over SEC company list (`company_directory.search_companies`). Returns `CompanySearchResponse`.

### `GET /api/sessions` / `GET /api/sessions/{session_id}`

Run history for compare/reload in UI (`session_store`).

### Other

- `GET /` → `web/index.html`
- `GET /health` → `{ "status": "ok", "llm_provider": "openai"|"ollama"|"demo" }`
- Static assets mounted at `/web/…`

### OpenAPI

- http://localhost:8000/docs when running `uvicorn app.main:app --reload`

---

## LangGraph workflow (`app/graph.py`)

Entry → conditional edges (stop on `errors`):

1. **resolve_cik** — `company_directory.resolve_ticker` (not a hardcoded map)
2. **fetch_sec_data** — submissions + company facts (`sec_client`, optional `sec_cache`)
3. **extract_evidence** — metadata + XBRL financials
4. **generate_report** — `ReportGenerator`
5. **evaluate_report** — `EvalChain`
6. **finalize_response** — `CompanySignalResponse`

Exported: `compiled_graph`. TODOs in file: checkpointing, eval repair loop, 10-K text, competitor branch.

---

## Ticker → CIK

**Do not hardcode in `main.py`.** Use `app/company_directory.py`:

- Downloads https://www.sec.gov/files/company_tickers.json (cached locally)
- `resolve_ticker(ticker)` → `CompanyRecord` or `None`
- `search_companies(query, limit)` for UI typeahead
- Preloaded on app startup via `lifespan` → `preload_directory()`

Unknown ticker → graph error `UNKNOWN_TICKER` → HTTP 400.

---

## SEC client (`app/sec_client.py`)

EDGAR (async httpx, `User-Agent` from settings):

- `/submissions/CIK##########.json`
- `/api/xbrl/companyfacts/CIK##########.json`

### Evidence from company facts (latest values)

`Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `OperatingIncomeLoss`, `ResearchAndDevelopmentExpense`, `SellingGeneralAndAdministrativeExpense`, `NetIncomeLoss`

### Evidence from submissions metadata

Company name, SIC, fiscal year end, entity type.

Evidence items use numeric refs `[0]`, `[1]`, … in prompts and report citations.

---

## Report generation (`app/report_generator.py`)

- `ReportGenerator.generate(...)` → `SignalReport`
- Chat model from `llm_factory.create_chat_model()` (OpenAI or Ollama)
- `demo` / `DEMO_MODE` uses fixtures in `app/demo.py`
- Parse structured JSON into `SignalReport`

### Prompt rules (`app/prompts.py`)

Enterprise competitive-intelligence analyst: separate **signal** from **noise**; evidence-only claims; no invented numbers; no trends without comparative evidence; weak evidence → low confidence.

---

## Evaluation (`app/eval_chain.py`)

- `EvalChain.evaluate(report, evidence)` → `EvalResult`
- LLM-as-judge evidence auditor
- `passed`, `claim_support_score`, `unsupported_claims`, `warnings`
- If `claim_support_score < CLAIM_SUPPORT_THRESHOLD` → `passed=false` + warning
- Placeholder comments for future OpenEvals (hallucination, numerical consistency, citations)
- App depends **only** on `EvalChain`, not OpenEvals directly

---

## Web UI (`web/`)

**Title:** SignalPath Intel  
**Subtitle:** AI competitive intelligence from public disclosures

- Company search (ticker/name) via `/api/companies/search`
- **Generate Signal Report** — prefers SSE stream endpoint for live logs
- Run history sidebar — reload past sessions from `/api/sessions`
- Sections: Executive Summary, Top Signals, Noise, Risks, Recommended Actions, Evidence Table, Evaluation Result

---

## Setup & run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.local.example .env.local
# Optional: OPENAI_API_KEY=sk-...
# Or: Ollama — ollama serve, set OLLAMA_MODEL from `ollama list`
# Or: DEMO_MODE=true for fixtures only

uvicorn app.main:app --reload
```

- App: http://localhost:8000
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

**Common startup failure:** stale import of `TICKER_CIK_MAP` from `app.graph` — removed; use `company_directory` only.

---

## Design constraints

- Modular, readable, typed, minimal
- MVP runs locally first; Ollama-friendly without OpenAI key
- Focused diffs — no drive-by refactors
- Do not commit unless the user asks
- Do not add scope (auth, DB, Docker, React, workers) without explicit ask
- Vercel: no persistent `data/sessions` or `data/sec_cache` on serverless — document if deploying

---

## Repo status

| Item | Status |
|------|--------|
| `app/config.py` | Done |
| `app/schemas.py` | Done |
| `app/prompts.py` | Done |
| `app/sec_client.py` | Done |
| `app/sec_cache.py` | Done |
| `app/company_directory.py` | Done |
| `app/report_generator.py` | Done |
| `app/eval_chain.py` | Done |
| `app/graph.py` | Done |
| `app/run_stream.py` | Done |
| `app/llm_factory.py` | Done |
| `app/session_store.py` | Done |
| `app/main.py` | Done (SignalPath Intel) |
| `web/` | Done |
| `requirements.txt` | Done |
| `.env.local.example` | Done |
| `.gitignore` | Done (`.env.local`) |
| `README.md` | Done |
| `api/index.py`, `vercel.json` | Done |
| `tests/test_company_directory.py` | Done |
| `app/scorer.py`, `tests/test_scorer.py`, `static/` | Legacy — remove when cleaning up |

---

## Next steps (not MVP)

1. 10-K filing retrieval and section parsing (Item 1, 1A, 1C, 7)
2. OpenEvals inside `EvalChain`
3. Competitor comparison branch in LangGraph
4. Eval repair loop when audit fails
5. Source citation URLs on evidence rows
6. Report export (Markdown, PDF)
7. Delta analysis across filing years
8. LangGraph checkpointing for long runs
9. Production session/cache storage (not local JSON on Vercel)

---

## Curl smoke test

```bash
curl -s -X POST http://localhost:8000/reports/company-signal \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "MSFT",
    "company_name": "Microsoft",
    "lens": "AI strategy, cloud growth, cybersecurity risk, margin pressure",
    "competitors": ["CRM", "NOW", "TEAM"]
  }' | python -m json.tool
```

Requires network to SEC; LLM via OpenAI key, running Ollama, or `DEMO_MODE=true`.
