"""Tests for db.execute against a real backend (sqlite via SQLAlchemy).

The same code path runs against oracle / postgres / mysql / mssql — only the
DATABASE_URL changes. Sqlite is the canonical test target because it ships
with Python and needs no driver install or running server.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import polars as pl
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from carta import db
from carta.config import Config


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[Connection]:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.sqlite'}")
    with engine.connect() as c:
        c.execute(
            text(
                "CREATE TABLE students (student_id INTEGER, program_code TEXT, "
                "credits INTEGER, term_code TEXT)"
            )
        )
        c.execute(
            text("INSERT INTO students VALUES (:a, :b, :c, :d)"),
            [
                {"a": 1001, "b": "CS", "c": 15, "d": "202680"},
                {"a": 1002, "b": "MATH", "c": 12, "d": "202680"},
                {"a": 1003, "b": "ENGL", "c": 9, "d": "202610"},
            ],
        )
        c.commit()
        yield c


def _cfg(database_url: str) -> Config:
    return Config(
        definitions_dir=Path("/tmp/definitions"),
        output_dir=Path("/tmp/out"),
        database_url=database_url,
        keyring_service="carta_test",
        active=[],
    )


def test_execute_returns_dataframe_with_named_columns(conn: Connection) -> None:
    df = db.execute(
        conn, "SELECT student_id, program_code FROM students ORDER BY student_id", {}
    )
    assert df.columns == ["student_id", "program_code"]
    assert df.height == 3
    assert df["student_id"].to_list() == [1001, 1002, 1003]
    assert df["program_code"].to_list() == ["CS", "MATH", "ENGL"]


def test_execute_binds_named_params(conn: Connection) -> None:
    df = db.execute(
        conn,
        "SELECT student_id FROM students WHERE term_code = :term_code ORDER BY student_id",
        {"term_code": "202680"},
    )
    assert df["student_id"].to_list() == [1001, 1002]


def test_execute_resolves_callable_params(conn: Connection) -> None:
    def term() -> str:
        return "202610"

    df = db.execute(
        conn,
        "SELECT student_id FROM students WHERE term_code = :term_code",
        {"term_code": term},
    )
    assert df["student_id"].to_list() == [1003]


def test_execute_returns_empty_frame_when_no_rows(conn: Connection) -> None:
    df = db.execute(
        conn,
        "SELECT student_id, program_code FROM students WHERE student_id = :id",
        {"id": -1},
    )
    assert df.height == 0


def test_execute_returns_empty_frame_for_ddl(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'ddl.sqlite'}")
    with engine.connect() as c:
        df = db.execute(c, "CREATE TABLE x (a INTEGER)", {})
        assert df.shape == (0, 0)


def test_execute_callable_resolved_once_per_call(conn: Connection) -> None:
    calls = {"n": 0}

    def term() -> str:
        calls["n"] += 1
        return "202680"

    db.execute(
        conn,
        "SELECT student_id FROM students WHERE term_code = :term_code",
        {"term_code": term},
    )
    assert calls["n"] == 1


def test_dataframe_types_preserved(conn: Connection) -> None:
    df = db.execute(
        conn, "SELECT student_id, program_code, credits FROM students LIMIT 1", {}
    )
    assert df.schema["student_id"] == pl.Int64
    assert df.schema["program_code"] == pl.Utf8
    assert df.schema["credits"] == pl.Int64


def test_connect_sqlite_no_username_no_password(tmp_path: Path) -> None:
    cfg = _cfg(f"sqlite:///{tmp_path / 'auth.sqlite'}")
    assert db.get_password(cfg, prompt=False) is None
    with db.connect(cfg) as c:
        assert c.execute(text("SELECT 1")).scalar() == 1


def test_get_password_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(db.PASSWORD_ENV, "from-env")
    cfg = _cfg("postgresql+psycopg://analyst@dbhost/dbname")
    assert db.get_password(cfg, prompt=False) == "from-env"


def test_reset_password_rejected_when_no_username(tmp_path: Path) -> None:
    cfg = _cfg(f"sqlite:///{tmp_path / 'a.sqlite'}")
    with pytest.raises(db.DbError, match="no username"):
        db.reset_password(cfg)


def test_invalid_database_url_raises(tmp_path: Path) -> None:
    cfg = _cfg("not a url at all")
    with pytest.raises(db.DbError, match="invalid DATABASE_URL"):
        db.get_password(cfg, prompt=False)
