# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

RoleScout is an agentic job-search engine for discovering, evaluating, and managing relevant opportunities. It is a Python project in early development.

## Tech Stack

- **Language:** Python 3.12
- **Package manager:** uv
- **Linting/formatting:** ruff
- **Type checking:** mypy
- **Testing:** pytest + pytest-httpx
- **UI:** Streamlit
- **Storage:** SQLite via SQLModel
- **LLM scoring:** Anthropic SDK (`claude-sonnet-4-6`) with prompt caching

## Commands

```bash
uv sync                                          # install deps
uv run ruff check rolescout/ tests/             # lint
uv run ruff format rolescout/ tests/            # format
uv run mypy rolescout/                           # type check
uv run pytest tests/ -v                         # run tests

# First-time setup
cp resume.md.template resume.md                 # fill in your resume
cp .env.example .env                            # add your API keys

# Run the pipeline
uv run rolescout fetch-and-score                 # fetch + score all sources
uv run rolescout fetch-and-score --sources remotive --limit 10 --dry-run
uv run rolescout show --fit strong --top 10     # CLI view
uv run rolescout ui                              # launch Streamlit dashboard
# or directly: uv run streamlit run rolescout/ui/app.py
```

## Architecture

```
rolescout/
├── config.py        # pydantic-settings — reads .env
├── models.py        # Job (transient), ScoredJob (SQLite table), FitLevel enum
├── fetchers/        # one file per source; all implement BaseFetcher.fetch() -> list[Job]
│   ├── remotive.py  # free, no key
│   ├── themuse.py   # free, no key
│   ├── adzuna.py    # skipped if ADZUNA_APP_ID/KEY absent
│   └── jsearch.py   # RapidAPI — aggregates LinkedIn/Indeed/Glassdoor; skipped if RAPIDAPI_KEY absent
├── scorer.py        # JobScorer: batches jobs, calls Claude API with prompt caching on resume
├── ranker.py        # compute_scores() + rank_jobs(); composite = 50% fit + 30% recency + 10% comp + 10% location
├── storage.py       # init_db(), save_jobs() (upsert), load_jobs() (filtered)
├── cli.py           # click CLI entry point
└── ui/app.py        # Streamlit dashboard
```

**Pipeline flow:** `fetchers → scorer → ranker → storage → ui/cli`

**Scoring:** Claude receives the resume (prompt-cached) + a batch of job descriptions and returns JSON with `fit_level` (strong/medium/low), `fit_score` (0–1), and `reasoning`. The ranker combines this with recency, compensation overlap, and location match into a `composite_score`.

**Key env vars:** `ANTHROPIC_API_KEY` (required), `RAPIDAPI_KEY` (JSearch), `ADZUNA_APP_ID` + `ADZUNA_API_KEY`, `TARGET_ROLE`, `TARGET_LOCATION`, `TARGET_SALARY_MIN/MAX`.

## Design Decisions

**Why JSearch instead of LinkedIn/Indeed APIs:** Both native APIs are deprecated/closed to new signups. JSearch on RapidAPI (free tier: 10 req/day, paid ~$10/month for 500/day) aggregates LinkedIn, Indeed, Glassdoor, and ZipRecruiter under one endpoint.

**Why `Job` is transient (not `table=True`):** The raw fetched job only lives in memory during a pipeline run. `ScoredJob` is the single persisted entity, avoiding a two-table join on every dashboard query.

**Why `tags` is a comma-separated string in `ScoredJob`:** SQLite has no native array column type. Tags are low-priority filter criteria so a simple string is sufficient.

**Prompt caching pattern in `scorer.py`:** The system prompt is two blocks — a small static instructions block (not cached) followed by the resume block with `cache_control: {"type": "ephemeral"}`. Anthropic caches everything up to and including that marker, so the resume (~1–3k tokens) is only billed at full price on the first batch call per session.

**Scoring batch size (default 10):** Each job description is truncated to 2000 chars. At ~500 tokens/JD + ~2000 tokens for resume/instructions, a batch of 10 fits comfortably in the context window while reducing API calls ~10× vs. one-job-per-call.

**Composite score weights:** fit 50%, recency 30%, compensation 10%, location 10%. Fit dominates; recency is the second signal to prefer fresh postings. Weights are module-level constants in `ranker.py` — easy to tune.

## Gitignored Runtime Files

These exist locally but are never committed:
- `resume.md` — user's resume (template at `resume.md.template`)
- `.env` — API keys and search config (template at `.env.example`)
- `rolescout.db` — SQLite database
- `PLAN.md` — implementation plan reference copy

## Tests

```
tests/
├── conftest.py              # Job + ScoredJob fixtures
├── test_models.py           # tags coercion validator
├── test_ranker.py           # all scoring functions + composite weights
├── test_scorer.py           # JSON parse, fallback on bad JSON, cache_control present
├── test_storage.py          # save/load roundtrip, upsert, filters (in-memory SQLite)
└── fetchers/
    ├── test_remotive.py     # HTTP mock via pytest-httpx
    └── test_jsearch.py      # HTTP mock; skip-when-no-key, id prefix, error handling
```

Fetcher tests use `pytest-httpx` to mock HTTP responses without real network calls. Storage tests use `monkeypatch` to redirect `settings.db_path` to a temp file.

## Adding a New Fetcher

1. Create `rolescout/fetchers/yourname.py` — subclass `BaseFetcher`, set `source_name`, implement `fetch() -> list[Job]`. Return `[]` on any error (log, don't raise).
2. Add to `get_all_fetchers()` in `rolescout/fetchers/__init__.py`.
3. Add a corresponding `tests/fetchers/test_yourname.py` using `pytest-httpx`.
4. If it needs an API key, add the field to `rolescout/config.py` and `.env.example`, and skip in `fetch()` when the key is absent.
