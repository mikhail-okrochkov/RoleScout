# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

RoleScout is a personal job-search engine: fetches jobs from multiple public APIs, scores each against a resume using AI, ranks by a composite score, and presents results in a Streamlit dashboard.

## Tech Stack

- **Language:** Python 3.12, **package manager:** uv
- **Linting/formatting:** ruff, **type checking:** mypy, **testing:** pytest + pytest-httpx
- **UI:** Streamlit (dark theme via `.streamlit/config.toml`)
- **Storage:** SQLite via SQLModel
- **Primary scorer:** TypeSafe Jev SDK (`typesafe-sdk`) — structured scoring with probability distributions
- **Fallback scorer:** Anthropic SDK (`claude-sonnet-4-6`) with prompt caching — used when `TYPESAFE_API_KEY` is absent

## Commands

```bash
uv sync                                          # install deps
uv run ruff check rolescout/ tests/             # lint
uv run ruff format rolescout/ tests/            # format
uv run mypy rolescout/                           # type check
uv run pytest tests/ -v                         # run tests

# First-time setup
cp resume.md.template resume.md                 # fill in your resume
cp .env.example .env                            # add API keys (secrets)
cp config.yaml.example config.yaml             # add search preferences

# Run the pipeline
uv run rolescout fetch-and-score                 # fetch + score all sources
uv run rolescout fetch-and-score --sources remotive --limit 10 --dry-run
uv run rolescout show --fit strong --top 10
uv run rolescout ui                              # launch Streamlit dashboard
```

## Architecture

```
rolescout/
├── config.py        # pydantic-settings — merges .env (secrets) + config.yaml (preferences)
├── models.py        # Job (transient), ScoredJob (SQLite table), FitLevel enum
├── fetchers/        # one file per source; all implement BaseFetcher.fetch() -> list[Job]
│   ├── remotive.py  # free, no key; all results remote=True
│   ├── themuse.py   # free, no key
│   ├── adzuna.py    # skipped if ADZUNA_APP_ID/KEY absent
│   └── jsearch.py   # RapidAPI — aggregates LinkedIn/Indeed/Glassdoor; skipped if RAPIDAPI_KEY absent
├── scorer.py        # FitAssessment dataclass + Claude JobScorer (batch, prompt-cached)
├── jev_scorer.py    # JevScorer — 4 Score questions + 1 Choice; returns per-dimension scores
│                    #   and full probability distributions stored in scorer_details
├── ranker.py        # compute_scores() + rank_jobs(); composite = 80% fit + 10% comp + 10% location
├── geocoder.py      # Nominatim geocoding with haversine distance; JSON cache; 1 req/s rate limit
├── storage.py       # init_db(), save_jobs() (upsert), load_jobs() (filtered by fit/source/location/date)
├── cli.py           # click CLI: fetch-and-score, show, ui commands; --scorer [jev|claude]
└── ui/app.py        # Streamlit dashboard — Results tab + Analyze tab
```

**Pipeline:** `fetchers → deduplicate → scorer → ranker → storage → ui`

Each fetcher loops over all `target_roles` from config.yaml. Jobs containing any `exclude_keywords` are dropped before scoring.

## Configuration Split

Secrets live in `.env`, preferences in `config.yaml`. Both are gitignored.

- **`.env`**: `TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY`, `RAPIDAPI_KEY`, `ADZUNA_APP_ID`, `ADZUNA_API_KEY`, `DB_PATH`, `RESUME_PATH`
- **`config.yaml`**: `target_roles`, `target_location`, `target_salary_min/max`, `preferred_locations`, `acceptable_locations`, `location_radius_miles`, `exclude_keywords`, `adzuna_pages`, `jsearch_pages_per_role`, `batch_size`

pydantic-settings loads them via `settings_customise_sources` in priority order: init kwargs → env vars → `.env` → `config.yaml` → defaults.

## Scoring

**Jev scorer** (`jev_scorer.py`) — default when `TYPESAFE_API_KEY` is set:
- Sends `{resume, job}` state to TypeSafe with 4 `Score` questions (skills, seniority, domain, responsibilities) and 1 `Choice` question (seniority direction)
- Each `Score` returns `.score` (0–3), `.probabilities` (`dict[int, float]` keyed by level), and `.legend`
- Composite fit = `0.40·skills + 0.30·seniority + 0.15·domain + 0.15·responsibilities` (normalized to 0–1)
- All probability distributions are serialized into `scorer_details` (JSON) on `ScoredJob` for UI display

**Claude scorer** (`scorer.py`) — fallback:
- Batches jobs (default 10), sends resume (prompt-cached) + job descriptions, returns JSON with `fit_level`/`fit_score`/`reasoning`

**Composite score** (ranker.py): `0.80 × fit + 0.10 × compensation + 0.10 × location`
- Recency is intentionally excluded (jobs get reposted; dates are unreliable)
- Compensation: job floor ≥ target min → 1.0; ceiling reaches target min → 0.7; no overlap → 0.0
- Location: remote → 1.0; preferred city match → 1.0; acceptable city match → 0.6; geocoded suburb within radius → same tiers; unmatched → 0.0

## ScoredJob Schema

Key fields beyond the basics:
- `scorer`: `"jev"` or `"claude"`
- `score_skills`, `score_seniority`, `score_domain`, `score_responsibilities`: per-dimension 0–1 floats (Jev only)
- `seniority_direction`: `"underqualified"` | `"well_matched"` | `"overqualified"` (Jev only)
- `scorer_details`: JSON blob with probability distributions per dimension (Jev only)
- `fit_reasoning`: AI reasoning text (Claude only; empty string for Jev)

Schema migrations use `ALTER TABLE ADD COLUMN` in `init_db()`, wrapped in try/except — safe to run repeatedly.

## UI

Two tabs:
- **Results** — filtered job list with fit/score/salary/location columns; expander shows reasoning, per-dimension Jev scores with probability distributions, and composite/comp/location bars. Jobs requiring clearance are flagged with 🚩.
- **Analyze** — paste any job description, optionally enter salary/URL, score on demand with either scorer

Sidebar controls: fit level filter, source filter, remote toggle, location tier dropdown, date range, Fetch New Jobs button (runs `rolescout fetch-and-score` as subprocess with 5-minute timeout).

## Gitignored Runtime Files

- `resume.md` — template at `resume.md.template`
- `.env` — template at `.env.example`
- `config.yaml` — template at `config.yaml.example`
- `rolescout.db` — SQLite database
- `geocode_cache.json` — Nominatim geocoding cache (lives alongside the DB)

## Docker

```bash
docker compose up --build   # build and start
docker compose down -v      # stop and delete the DB volume
```

The DB lives in a named volume (`rolescout_data`). `resume.md` and `config.yaml` are bind-mounted read-only. Secrets come from `.env` via `env_file`.

## Tests

```
tests/
├── conftest.py              # Job + ScoredJob fixtures
├── test_models.py           # tags coercion validator
├── test_ranker.py           # recency/comp/location scoring + composite weights
├── test_scorer.py           # JSON parse, fallback on bad JSON, cache_control present
├── test_storage.py          # save/load roundtrip, upsert, filters (in-memory SQLite)
└── fetchers/
    ├── test_remotive.py     # pytest-httpx mocks
    └── test_jsearch.py      # skip-when-no-key, id prefix, error handling
```

Fetcher tests pin `target_roles` to a single role via `monkeypatch` to avoid registering multiple mock responses.

## Adding a New Fetcher

1. Create `rolescout/fetchers/yourname.py` — subclass `BaseFetcher`, set `source_name`, implement `fetch() -> list[Job]`. Return `[]` on any error (log, don't raise).
2. Add to `get_all_fetchers()` in `rolescout/fetchers/__init__.py`.
3. Add `tests/fetchers/test_yourname.py` with pytest-httpx mocks.
4. If an API key is needed: add to `config.py` and `.env.example`, skip in `fetch()` when absent.
