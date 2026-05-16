"""Test fixtures."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "student_id": [1001, 1002, 1003],
            "program_code": ["CS", "MATH", "ENGL"],
            "credits": [15, 12, 9],
        }
    )


def write_project(
    tmp_path: Path,
    *,
    active: list[str],
    database_url: str = "sqlite:///",
    definitions: dict[str, tuple[str, str]] | None = None,
) -> Path:
    """Build a config.py + definitions/ tree in tmp_path.

    `definitions` maps stem -> (py_body, sql_body).
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "definitions").mkdir(exist_ok=True)
    (tmp_path / "out").mkdir(exist_ok=True)
    (tmp_path / "config.py").write_text(
        "from pathlib import Path\n"
        "REPO_ROOT = Path(__file__).resolve().parent\n"
        "DEFINITIONS_DIR = REPO_ROOT / 'definitions'\n"
        "OUTPUT_DIR = REPO_ROOT / 'out'\n"
        f"DATABASE_URL = {database_url!r}\n"
        "KEYRING_SERVICE = 'carta_test'\n"
        f"ACTIVE = {active!r}\n"
    )
    for stem, (py_body, sql_body) in (definitions or {}).items():
        (tmp_path / "definitions" / f"{stem}.py").write_text(py_body)
        (tmp_path / "definitions" / f"{stem}.sql").write_text(sql_body)
    return tmp_path
