# SignalPath Intel

AI competitive-intelligence analyst for public companies. SignalPath Intel pulls SEC EDGAR data, generates a source-grounded **signal vs noise** report through LangGraph, and runs an evidence audit before returning results.

## What it does

1. Accepts a ticker, company name, business lens, and competitor context.
2. Fetches SEC submissions and XBRL company facts.
3. Extracts financial and metadata evidence.
4. Generates a structured competitive-intelligence report (LangChain + LangGraph).
5. Audits claims against evidence (LLM-as-judge eval chain).

Eval failures are returned explicitly — the report is not hidden when the audit fails.

## Stack

- Python 3.11, FastAPI, Pydantic, Pydantic Settings
- httpx (async SEC client)
- LangChain, langchain-openai, LangGraph
- Plain HTML/CSS/vanilla JS frontend
- Vercel-compatible entrypoint (`api/index.py`)

## Setup

On macOS, use `python3` (there is often no `python` command):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.local.example .env.local
```

### No OpenAI key? Use Ollama (recommended locally)

With Ollama running (`ollama serve`), leave `OPENAI_API_KEY` empty. The app uses **Ollama by default** (`LLM_PROVIDER=auto`).

1. See which models you have: `ollama list`
2. Set the model in `.env.local`:

```bash
OLLAMA_MODEL=llama3.2   # use a name from `ollama list`
```

3. Install deps and run (see below). Check http://localhost:8000/health — it should show `"llm_provider": "ollama"`.

**Fixture demo** (no LLM at all): set `DEMO_MODE=true` in `.env.local`.

**OpenAI:** set `OPENAI_API_KEY=sk-...` — auto mode prefers OpenAI when the key is present.

If you already have `.venv` and `pip install` succeeded, run `pip install -r requirements.txt` again for `langchain-ollama`.

## Run locally

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

- App: http://localhost:8000
- API docs: http://localhost:8000/docs

### Run history & SEC cache (local)

Each successful report is saved under `data/sessions/` (config: `SESSIONS_ENABLED`). The UI **Run history** list lets you reload a past run for comparison (same report, evidence, and pipeline log).

SEC EDGAR responses are cached per CIK under `data/sec_cache/` (`SEC_CACHE_ENABLED`, default TTL 24h). Re-running the same ticker skips the internet SEC fetch and logs `SEC data loaded from local cache`.

Disable either feature in `.env.local`:

```bash
SESSIONS_ENABLED=false
SEC_CACHE_ENABLED=false
```

**Note:** File-based sessions/cache work for local dev. Vercel serverless has no persistent disk — use a database or object storage for production history.

## Curl test

```bash
curl -X POST http://localhost:8000/reports/company-signal \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "MSFT",
    "company_name": "Microsoft",
    "lens": "AI strategy, cloud growth, cybersecurity risk, margin pressure",
    "competitors": ["CRM", "NOW", "TEAM"]
  }'
```

Supported tickers (MVP map): MSFT, AAPL, GOOGL, GOOG, AMZN, META, CRM, NOW, TEAM, ADBE, ORCL.

## Vercel deployment

1. Install the Vercel CLI (if needed):

```bash
npm i -g vercel
```

2. Log in:

```bash
vercel login
```

3. Deploy:

```bash
vercel
```

4. Set environment variables in the Vercel project (dashboard or CLI):

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `SEC_USER_AGENT`
- `SEC_BASE_URL`
- `CLAIM_SUPPORT_THRESHOLD`

5. Redeploy production:

```bash
vercel --prod
```

**Note:** The MVP is synchronous. If reports time out on Vercel, move the LangGraph workflow to a background worker or longer-running backend (Cloud Run, Railway, Render, Fly.io, AWS ECS) while keeping Vercel as the web shell.

## Project layout

```
api/index.py          # Vercel ASGI entry
app/
  main.py             # FastAPI routes + static files
  config.py           # settings from env / .env.local
  schemas.py
  sec_client.py
  report_generator.py
  eval_chain.py
  graph.py            # LangGraph workflow
  prompts.py
web/                  # Browser demo shell
requirements.txt
vercel.json
.env.local.example
```

## Next steps

1. Add real ticker-to-CIK lookup.
2. Add 10-K filing document retrieval.
3. Parse Item 1, Item 1A, Item 1C, and Item 7.
4. Add OpenEvals inside `EvalChain`.
5. Add competitor comparison branch in the graph.
6. Add report export (Markdown, PDF).
7. Add source citations with direct filing URLs.
8. Add delta analysis across filing years.
9. Add eval repair loop when claims fail the audit.
