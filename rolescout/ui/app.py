from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta

import streamlit as st

st.set_page_config(page_title="RoleScout", page_icon="🔍", layout="wide")

from rolescout.storage import get_sources, init_db  # noqa: E402

init_db()

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.header("Filters")

fit_filter = st.sidebar.multiselect(
    "Fit Level",
    options=["strong", "medium", "low"],
    default=["strong", "medium"],
)

all_sources = get_sources()
source_filter = st.sidebar.multiselect(
    "Source",
    options=all_sources,
    default=[],
    placeholder="All sources",
)

remote_only = st.sidebar.toggle("Remote only", value=False)

_LOCATION_OPTIONS = {
    "Remote / Preferred cities": 1.0,
    "Acceptable cities": 0.6,
    "Any location": 0.0,
}
location_filter = st.sidebar.selectbox(
    "Location",
    options=list(_LOCATION_OPTIONS.keys()),
    index=0,
)
min_location_score = _LOCATION_OPTIONS[location_filter]

today = date.today()
default_start = today - timedelta(days=90)
date_range = st.sidebar.date_input(
    "Posted between",
    value=(default_start, today),
    max_value=today,
)

st.sidebar.divider()

if st.sidebar.button("🔄 Fetch New Jobs", use_container_width=True):
    import subprocess
    import sys
    from pathlib import Path

    rolescout_bin = Path(sys.executable).parent / "rolescout"
    timed_out = False
    with st.spinner("Fetching and scoring jobs… this may take a minute."):
        try:
            result = subprocess.run(
                [str(rolescout_bin), "fetch-and-score"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            output = result.stdout + result.stderr
            success = result.returncode == 0
        except subprocess.TimeoutExpired as e:
            timed_out = True
            output = (e.stdout or "") + (e.stderr or "")
            success = False

    if timed_out:
        st.sidebar.error("Timed out after 5 minutes.")
    elif success:
        st.sidebar.success("Fetch complete.")
        st.cache_data.clear()
        st.rerun()
    else:
        st.sidebar.error("Fetch failed.")

    if output:
        with st.sidebar.expander("Output" if success else "Error output", expanded=not success):
            st.code(output)

if st.sidebar.button("Refresh from DB", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# ── Load data ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def _load(
    fit_levels: list[str],
    sources: list[str],
    remote: bool,
    min_loc_score: float,
    start: date,
    end: date,
) -> list:
    from rolescout.models import FitLevel as _FL
    from rolescout.storage import load_jobs as _lj

    fl = [_FL(f) for f in fit_levels] if fit_levels else None
    src = sources if sources else None
    min_dt = datetime(start.year, start.month, start.day, tzinfo=UTC)
    max_dt = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=UTC)
    return _lj(
        fit_levels=fl,
        sources=src,
        remote_only=remote,
        min_location_score=min_loc_score,
        min_date=min_dt,
        max_date=max_dt,
    )


date_start, date_end = (date_range if len(date_range) == 2 else (default_start, today))
jobs = _load(fit_filter, source_filter, remote_only, min_location_score, date_start, date_end)

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🔍 RoleScout")

counts = Counter(j.fit_level.value for j in jobs)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total", len(jobs))
m2.metric("Strong", counts.get("strong", 0))
m3.metric("Medium", counts.get("medium", 0))
m4.metric("Low", counts.get("low", 0))

if jobs:
    import pandas as pd  # type: ignore[import-untyped]

    df = pd.DataFrame(
        [
            {
                "fit_level": j.fit_level.value,
                "composite_score": round(j.composite_score, 3),
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "remote": j.remote,
                "source": j.source,
                "posted_at": j.posted_at,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "url": j.url,
                "reasoning": j.fit_reasoning,
            }
            for j in jobs
        ]
    )
    st.download_button(
        "Export CSV",
        df.to_csv(index=False),
        file_name="rolescout_jobs.csv",
        mime="text/csv",
    )

st.divider()

# ── Helpers ───────────────────────────────────────────────────────────────────
_FIT_ICON = {"strong": "🟢", "medium": "🟡", "low": "🔴"}
_FIT_COLOR = {"strong": "green", "medium": "orange", "low": "red"}


def _salary_str(salary_min: int | None, salary_max: int | None) -> str:
    if salary_min and salary_max:
        return f"${salary_min // 1000}k – ${salary_max // 1000}k"
    if salary_min:
        return f"${salary_min // 1000}k+"
    if salary_max:
        return f"up to ${salary_max // 1000}k"
    return "—"


def _location_str(location: str, remote: bool) -> str:
    if remote and location.lower() in ("", "unknown", "remote"):
        return "Remote"
    if remote:
        return f"{location} (Remote)"
    return location or "—"


# ── Job Cards ─────────────────────────────────────────────────────────────────
if not jobs:
    st.info(
        "No jobs match your filters, or the database is empty. "
        "Run `rolescout fetch-and-score` to populate it."
    )
else:
    # Column header row
    h_fit, h_title, h_location, h_salary, h_score = st.columns([1, 4, 2, 2, 1])
    h_fit.caption("Fit")
    h_title.caption("Role / Company")
    h_location.caption("Location")
    h_salary.caption("Salary")
    h_score.caption("Score")
    st.divider()

    for job in jobs:
        icon = _FIT_ICON.get(job.fit_level.value, "⚪")
        color = _FIT_COLOR.get(job.fit_level.value, "gray")

        # ── Always-visible summary row ────────────────────────────────────────
        c_fit, c_title, c_location, c_salary, c_score = st.columns([1, 4, 2, 2, 1])

        c_fit.markdown(f":{color}[{icon} **{job.fit_level.value.upper()}**]")
        c_title.markdown(f"**{job.title}**  \n{job.company}")
        c_location.markdown(_location_str(job.location, job.remote))
        c_salary.markdown(_salary_str(job.salary_min, job.salary_max))
        c_score.markdown(f"**{job.composite_score:.2f}**")

        # ── Expandable detail section ─────────────────────────────────────────
        with st.expander("Details"):
            left, right = st.columns([3, 1])

            with left:
                st.markdown(f"**Reasoning:** {job.fit_reasoning}")
                if job.posted_at:
                    st.caption(f"Posted {job.posted_at.strftime('%Y-%m-%d')} · {job.source}")
                else:
                    st.caption(job.source)
                st.link_button("View Job →", job.url)

            with right:
                st.markdown("**Score breakdown**")
                st.progress(job.fit_score, text=f"Fit {job.fit_score:.2f}")
                st.progress(job.recency_score, text=f"Recency {job.recency_score:.2f}")
                st.progress(job.compensation_score, text=f"Comp {job.compensation_score:.2f}")
                st.progress(job.location_score, text=f"Location {job.location_score:.2f}")

        st.divider()
