from __future__ import annotations

from rolescout.models import Job


def test_tags_coerce_from_list() -> None:
    job = Job(
        id="x", title="T", company="C", location="L",
        description="D", url="U", source="s", tags=["python", "fastapi"],
    )
    assert job.tags == ["python", "fastapi"]


def test_tags_coerce_from_string() -> None:
    job = Job(
        id="x", title="T", company="C", location="L",
        description="D", url="U", source="s", tags="python, fastapi",  # type: ignore[arg-type]
    )
    assert job.tags == ["python", "fastapi"]


def test_tags_coerce_from_none() -> None:
    job = Job(
        id="x", title="T", company="C", location="L",
        description="D", url="U", source="s", tags=None,  # type: ignore[arg-type]
    )
    assert job.tags == []
