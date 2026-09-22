from __future__ import annotations

import json
import re
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


_CLEARANCE_RE = re.compile(
    r"\b(clearance|ts[/ -]?sci|top[\s\-]secret|polygraph|secret[\s\-]clearance|clearable)\b",
    re.IGNORECASE,
)


def _requires_clearance(title: str, tags: str, reasoning: str) -> bool:
    return bool(_CLEARANCE_RE.search(f"{title} {tags} {reasoning}"))


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_results, tab_analyze = st.tabs(["🔍 Results", "📋 Analyze Job"])

# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Results
# ══════════════════════════════════════════════════════════════════════════════
with tab_results:
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

    if not jobs:
        st.info(
            "No jobs match your filters, or the database is empty. "
            "Run `rolescout fetch-and-score` to populate it."
        )
    else:
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
            _cleared = _requires_clearance(job.title, job.tags, job.fit_reasoning)

            c_fit, c_title, c_location, c_salary, c_score = st.columns([1, 4, 2, 2, 1])
            c_fit.markdown(f":{color}[{icon} **{job.fit_level.value.upper()}**]")
            _title_flag = "  🚩" if _cleared else ""
            c_title.markdown(f"**{job.title}**{_title_flag}  \n{job.company}")
            c_location.markdown(_location_str(job.location, job.remote))
            c_salary.markdown(_salary_str(job.salary_min, job.salary_max))
            c_score.markdown(f"**{job.composite_score:.2f}**")

            with st.expander("Details"):
                left, right = st.columns([2, 1])
                with left:
                    if _cleared:
                        st.error("🚩 Clearance likely required — skip this one.")
                    st.markdown(f"**Reasoning:** {job.fit_reasoning}")
                    _scorer_label = "🤖 Jev" if job.scorer == "jev" else "✦ Claude"
                    if job.posted_at:
                        st.caption(
                            f"Posted {job.posted_at.strftime('%Y-%m-%d')} "
                            f"· {job.source} · {_scorer_label}"
                        )
                    else:
                        st.caption(f"{job.source} · {_scorer_label}")
                    if job.url:
                        st.link_button("View Job →", job.url)
                with right:
                    st.markdown("**Score Breakdown**")
                    _details = (
                        json.loads(job.scorer_details) if job.scorer_details else {}
                    )
                    if job.score_skills is not None:
                        _DIMS = [
                            ("Skills", job.score_skills, "skills"),
                            ("Seniority", job.score_seniority, "seniority"),
                            ("Domain", job.score_domain, "domain"),
                            ("Responsibilities", job.score_responsibilities, "responsibilities"),
                        ]
                        _DIR_ICONS = {
                            "overqualified": "⬆️ Overqualified",
                            "well_matched": "✅ Well matched",
                            "underqualified": "⬇️ Underqualified",
                        }
                        for _dim_label, _dim_score, _dim_key in _DIMS:
                            if _dim_score is None:
                                continue
                            _header = f"**{_dim_label}** – {_dim_score:.0%}"
                            if _dim_key == "seniority" and job.seniority_direction:
                                _header += (
                                    "  "
                                    + _DIR_ICONS.get(
                                        job.seniority_direction, job.seniority_direction
                                    )
                                )
                            st.markdown(_header)
                            st.progress(_dim_score)
                            _dim_det = _details.get(_dim_key, {})
                            _probs = _dim_det.get("probabilities", [])
                            _labels = _dim_det.get("short_labels", [])
                            if _probs and _labels:
                                st.caption(
                                    " · ".join(
                                        f"{_l}: {_p:.0%}"
                                        for _l, _p in zip(_labels, _probs, strict=False)
                                    )
                                )
                        _sd = _details.get("seniority_direction", {})
                        _sd_probs = _sd.get("probabilities", {})
                        if _sd_probs:
                            st.caption(
                                "Direction: "
                                + " · ".join(
                                    f"{_k.replace('_', ' ')}: {_v:.0%}"
                                    for _k, _v in _sd_probs.items()
                                )
                            )
                    st.progress(job.fit_score, text=f"Composite fit {job.fit_score:.2f}")
                    st.progress(job.compensation_score, text=f"Comp {job.compensation_score:.2f}")
                    st.progress(job.location_score, text=f"Location {job.location_score:.2f}")

            st.divider()

# ── Salary extraction helper ──────────────────────────────────────────────────
def _extract_salary(text: str) -> tuple[int | None, int | None]:
    """Best-effort regex extraction of salary range from job description text."""
    import re

    # Strip commas so 200,000 becomes 200000
    clean = text.replace(",", "")

    # Try range patterns first: $200k-$300k, $200,000-$300,000, 200k to 300k, etc.
    range_patterns = [
        r'\$(\d+(?:\.\d+)?)\s*[kK]\s*[-–—to]+\s*\$?(\d+(?:\.\d+)?)\s*[kK]',
        r'\$(\d{4,})\s*[-–—to]+\s*\$?(\d{4,})',
        r'(\d+(?:\.\d+)?)\s*[kK]\s*[-–—to]+\s*(\d+(?:\.\d+)?)\s*[kK]',
    ]
    for pat in range_patterns:
        m = re.search(pat, clean, re.IGNORECASE)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            if lo < 1000:
                lo, hi = lo * 1000, hi * 1000
            return int(lo), int(hi)

    # Single value: $200k or $200,000
    single_patterns = [
        r'\$(\d+(?:\.\d+)?)\s*[kK]',
        r'\$(\d{5,})',
    ]
    for pat in single_patterns:
        m = re.search(pat, clean, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if val < 1000:
                val *= 1000
            return int(val), None

    return None, None


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Manual job analysis
# ══════════════════════════════════════════════════════════════════════════════
with tab_analyze:
    st.title("📋 Analyze a Job")
    st.caption("Paste any job description to score it against your resume.")

    col_left, col_right = st.columns([1, 1])

    with col_left:
        jd_title = st.text_input("Job title", placeholder="Staff Data Scientist")
        jd_company = st.text_input("Company", placeholder="Acme Corp")
        jd_location = st.text_input("Location", placeholder="Seattle, WA / Remote")

    with col_right:
        jd_salary_min = st.number_input(
            "Salary min ($)", min_value=0, value=0, step=10000, format="%d"
        )
        jd_salary_max = st.number_input(
            "Salary max ($)", min_value=0, value=0, step=10000, format="%d"
        )
        jd_url = st.text_input("Job URL (optional)", placeholder="https://...")

    jd_description = st.text_area(
        "Job description",
        placeholder="Paste the full job description here…",
        height=350,
    )

    from rolescout.config import settings as _cfg

    _scorer_options = ["Jev (TypeSafe)", "Claude"] if _cfg.typesafe_api_key else ["Claude"]
    scorer_choice = st.radio("Scorer", _scorer_options, horizontal=True)

    analyze_clicked = st.button("🔬 Analyze", type="primary", use_container_width=False)

    if analyze_clicked:
        if not jd_description.strip():
            st.warning("Paste a job description first.")
        else:
            from rolescout.models import Job
            from rolescout.ranker import compute_scores
            from rolescout.scorer import JobScorer

            # Use manually entered salary; fall back to extracting from description
            sal_min: int | None = jd_salary_min if jd_salary_min > 0 else None
            sal_max: int | None = jd_salary_max if jd_salary_max > 0 else None
            if sal_min is None or sal_max is None:
                ext_min, ext_max = _extract_salary(jd_description)
                if sal_min is None:
                    sal_min = ext_min
                if sal_max is None:
                    sal_max = ext_max
                if ext_min or ext_max:
                    st.info(f"Salary extracted from description: {_salary_str(ext_min, ext_max)}")

            job = Job(
                id="manual-analysis",
                title=jd_title or "Untitled",
                company=jd_company or "Unknown",
                location=jd_location or "Unknown",
                description=jd_description,
                url=jd_url or "",
                source="manual",
                posted_at=datetime.now(UTC),
                remote="remote" in jd_location.lower(),
                salary_min=sal_min,
                salary_max=sal_max,
            )

            spinner_label = "Scoring with Jev…" if "Jev" in scorer_choice else "Scoring with Claude…"  # noqa: E501
            with st.spinner(spinner_label):
                try:
                    if "Jev" in scorer_choice:
                        from rolescout.jev_scorer import JevScorer

                        resume = _cfg.resume_path.read_text(encoding="utf-8")
                        active_scorer = JevScorer(resume)
                    else:
                        active_scorer = JobScorer()  # type: ignore[assignment]
                    pairs = active_scorer.score_jobs([job])
                    _, assessment = pairs[0]
                    scores = compute_scores(job, assessment)
                except Exception as exc:
                    st.error(f"Scoring failed: {exc}")
                    assessment = None
                    scores = None

            if assessment and scores:
                fit = assessment.fit_level.value
                icon = _FIT_ICON.get(fit, "⚪")
                color = _FIT_COLOR.get(fit, "gray")

                st.divider()
                res_left, res_right = st.columns([2, 1])

                with res_left:
                    st.markdown(
                        f"### :{color}[{icon} {fit.upper()}]  "
                        f"— composite **{scores['composite_score']:.2f}**"
                    )
                    st.markdown(f"**Reasoning:** {assessment.reasoning}")

                with res_right:
                    st.markdown("**Score Breakdown**")
                    _a_details = assessment.scorer_details or {}
                    if assessment.score_skills is not None:
                        _A_DIMS = [
                            ("Skills", assessment.score_skills, "skills"),
                            ("Seniority", assessment.score_seniority, "seniority"),
                            ("Domain", assessment.score_domain, "domain"),
                            (
                                "Responsibilities",
                                assessment.score_responsibilities,
                                "responsibilities",
                            ),
                        ]
                        _A_DIR_ICONS = {
                            "overqualified": "⬆️ Overqualified",
                            "well_matched": "✅ Well matched",
                            "underqualified": "⬇️ Underqualified",
                        }
                        for _a_label, _a_score, _a_key in _A_DIMS:
                            if _a_score is None:
                                continue
                            _a_header = f"**{_a_label}** – {_a_score:.0%}"
                            if _a_key == "seniority" and assessment.seniority_direction:
                                _a_header += (
                                    "  "
                                    + _A_DIR_ICONS.get(
                                        assessment.seniority_direction,
                                        assessment.seniority_direction,
                                    )
                                )
                            st.markdown(_a_header)
                            st.progress(_a_score)
                            _a_dim_det = _a_details.get(_a_key, {})
                            _a_probs = _a_dim_det.get("probabilities", [])
                            _a_labels = _a_dim_det.get("short_labels", [])
                            if _a_probs and _a_labels:
                                st.caption(
                                    " · ".join(
                                        f"{_l}: {_p:.0%}"
                                        for _l, _p in zip(_a_labels, _a_probs, strict=False)
                                    )
                                )
                        _a_sd = _a_details.get("seniority_direction", {})
                        _a_sd_probs = _a_sd.get("probabilities", {})
                        if _a_sd_probs:
                            st.caption(
                                "Direction: "
                                + " · ".join(
                                    f"{_k.replace('_', ' ')}: {_v:.0%}"
                                    for _k, _v in _a_sd_probs.items()
                                )
                            )
                    st.progress(
                        scores["fit_score"], text=f"Composite fit {scores['fit_score']:.2f}"
                    )
                    st.progress(
                        scores["compensation_score"],
                        text=f"Comp {scores['compensation_score']:.2f}",
                    )
                    st.progress(
                        scores["location_score"],
                        text=f"Location {scores['location_score']:.2f}",
                    )
