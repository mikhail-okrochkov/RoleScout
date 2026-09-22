# RoleScout

Fetches jobs from multiple sources, scores each one against your resume using AI, and presents ranked results in a Streamlit dashboard.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- A [TypeSafe](https://typesafe.ai) API key (primary scorer)
- An [Anthropic](https://console.anthropic.com) API key (fallback scorer)
- Optionally: [RapidAPI / JSearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) and [Adzuna](https://developer.adzuna.com/) keys for more job sources

## Setup

**1. Copy and fill in your secrets**

```bash
cp .env.example .env
```

Edit `.env` and add your API keys. Only `TYPESAFE_API_KEY` or `ANTHROPIC_API_KEY` is required to score jobs. The rest unlock additional job sources.

**2. Write your resume**

```bash
cp resume.md.template resume.md
```

Edit `resume.md` with your actual experience. This is what the AI scores each job against. The file is gitignored.

**3. Configure your search preferences**

```bash
cp config.yaml.example config.yaml
```

Edit `config.yaml` to set your target roles, salary range, and preferred locations. The example file is fully documented. This file is also gitignored.

## Run

```bash
docker compose up --build
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

## Fetch jobs

From the dashboard sidebar, click **Fetch New Jobs** to run the full pipeline (fetch → score → save). This may take a few minutes depending on how many jobs are found.

Alternatively, run from the CLI inside the container:

```bash
docker compose exec rolescout rolescout fetch-and-score
docker compose exec rolescout rolescout fetch-and-score --sources remotive --dry-run
docker compose exec rolescout rolescout show --fit strong --top 10
```

## Job sources

| Source | Key required | Coverage |
|--------|-------------|----------|
| Remotive | No | Remote-only roles |
| The Muse | No | General |
| Adzuna | Yes (free) | US + international |
| JSearch | Yes (RapidAPI) | LinkedIn, Indeed, Glassdoor, ZipRecruiter |

Free tiers are sufficient for personal use. JSearch free tier is 10 requests/day; set `jsearch_pages_per_role: 1` in `config.yaml` to stay within it.

## Data

The SQLite database is stored in a named Docker volume (`rolescout_data`) and persists across container restarts. To reset it:

```bash
docker compose down -v
```
