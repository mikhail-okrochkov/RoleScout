from __future__ import annotations

import subprocess
import sys
from collections import Counter

import click
from rich.console import Console
from rich.table import Table

from rolescout.config import settings

console = Console()


def _is_excluded(title: str, description: str) -> bool:
    if not settings.exclude_keywords:
        return False
    text = f"{title} {description}".lower()
    return any(kw.lower() in text for kw in settings.exclude_keywords)




@click.group()
def cli() -> None:
    """RoleScout — fetch, score, and browse jobs matched to your resume."""


@cli.command("fetch-and-score")
@click.option(
    "--sources", "-s", multiple=True,
    help="Limit to specific sources: remotive, themuse, adzuna, jsearch.",
)
@click.option("--dry-run", is_flag=True, default=False, help="Score but do not save to DB.")
@click.option("--limit", "-n", default=0, type=int, help="Max jobs to score (0 = no limit).")
@click.option(
    "--scorer",
    type=click.Choice(["claude", "jev"]),
    default="jev",
    show_default=True,
    help="Scoring backend: jev (default, TypeSafe) or claude.",
)
def fetch_and_score(
    sources: tuple[str, ...], dry_run: bool, limit: int, scorer: str
) -> None:
    """Fetch jobs from all configured sources and score them against resume.md."""
    from rolescout.fetchers import get_all_fetchers
    from rolescout.ranker import rank_jobs
    from rolescout.scorer import JobScorer
    from rolescout.storage import init_db, save_jobs

    init_db()

    fetchers = get_all_fetchers()
    if sources:
        fetchers = [f for f in fetchers if f.source_name in sources]

    all_jobs = []
    for fetcher in fetchers:
        console.print(f"[cyan]Fetching from {fetcher.source_name}...[/]")
        jobs = fetcher.fetch()
        console.print(f"  [green]{len(jobs)} jobs fetched[/]")
        all_jobs.extend(jobs)

    # Deduplicate by id
    seen: set[str] = set()
    unique_jobs = []
    for j in all_jobs:
        if j.id not in seen:
            seen.add(j.id)
            unique_jobs.append(j)

    # Drop excluded jobs (e.g. clearance-required) before scoring
    if settings.exclude_keywords:
        before = len(unique_jobs)
        unique_jobs = [j for j in unique_jobs if not _is_excluded(j.title, j.description)]
        dropped = before - len(unique_jobs)
        if dropped:
            console.print(f"  [yellow]{dropped} jobs filtered by exclude_keywords[/]")


    if limit > 0:
        unique_jobs = unique_jobs[:limit]

    console.print(f"[bold]{len(unique_jobs)} unique jobs to score[/]")
    if not unique_jobs:
        console.print("[yellow]No jobs fetched — check your API keys and target role.[/]")
        return

    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TimeElapsedColumn,
    )

    if scorer == "jev" and settings.typesafe_api_key:
        from rolescout.jev_scorer import JevScorer

        resume = settings.resume_path.read_text(encoding="utf-8")
        active_scorer = JevScorer(resume)  # type: ignore[assignment]
        console.print("[cyan]Scorer: Jev (TypeSafe)[/]")
    else:
        if scorer == "jev":
            console.print("[yellow]TYPESAFE_API_KEY not set — falling back to Claude.[/]")
        active_scorer = JobScorer()
        console.print("[cyan]Scorer: Claude[/]")

    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scoring with Claude...", total=len(unique_jobs))
        pairs = active_scorer.score_jobs(
            unique_jobs,
            on_batch=lambda done, _total: progress.update(task, completed=done),
        )

    active_scorer_name = "jev" if (scorer == "jev" and settings.typesafe_api_key) else "claude"
    scored = rank_jobs(pairs, scorer=active_scorer_name)

    table = Table(title="Scoring Summary")
    table.add_column("Fit Level")
    table.add_column("Count", justify="right")
    counts = Counter(j.fit_level.value for j in scored)
    for level in ("strong", "medium", "low"):
        table.add_row(level, str(counts.get(level, 0)))
    console.print(table)

    if not dry_run:
        save_jobs(scored)
        console.print(f"[green]Saved {len(scored)} jobs to {settings.db_path}[/]")
    else:
        console.print("[yellow]Dry run — not saving to DB.[/]")


@cli.command("show")
@click.option(
    "--fit", "-f",
    type=click.Choice(["strong", "medium", "low"]),
    multiple=True,
    help="Filter by fit level (repeatable).",
)
@click.option("--top", "-n", default=20, help="Number of results to show.")
def show(fit: tuple[str, ...], top: int) -> None:
    """Display top-ranked jobs from the database."""
    from rolescout.models import FitLevel
    from rolescout.storage import load_jobs

    fit_levels = [FitLevel(f) for f in fit] if fit else None
    jobs = load_jobs(fit_levels=fit_levels, limit=top)

    if not jobs:
        console.print("[yellow]No jobs found. Run fetch-and-score first.[/]")
        return

    table = Table(title=f"Top {top} Jobs")
    table.add_column("Fit", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Title")
    table.add_column("Company")
    table.add_column("Source")
    table.add_column("URL")

    fit_colors = {"strong": "green", "medium": "yellow", "low": "red"}
    for j in jobs:
        color = fit_colors.get(j.fit_level.value, "white")
        table.add_row(
            f"[{color}]{j.fit_level.value}[/]",
            f"{j.composite_score:.2f}",
            j.title,
            j.company,
            j.source,
            j.url,
        )
    console.print(table)


@cli.command("ui")
def launch_ui() -> None:
    """Launch the Streamlit dashboard."""
    from pathlib import Path

    app_path = Path(__file__).parent / "ui" / "app.py"
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.headless", "true"],
        check=False,
    )
