"""Database connection, password handling, and query execution.

Backend is selected by `DATABASE_URL` in config.py — anything SQLAlchemy can
parse works (oracle, postgres, mysql, mssql, sqlite, ...). SQL files use
`:name` named parameters regardless of backend; SQLAlchemy translates to each
driver's native binding style.
"""

from __future__ import annotations

import contextlib
import getpass
import os
from typing import Any

import keyring
import polars as pl
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.url import URL, make_url

from carta.config import Config

PASSWORD_ENV = "CARTA_DB_PASSWORD"


class DbError(Exception):
    pass


def _parsed_url(cfg: Config) -> URL:
    try:
        return make_url(cfg.database_url)
    except Exception as e:
        raise DbError(f"invalid DATABASE_URL: {e}") from e


def _save_password(service: str, username: str, password: str) -> None:
    try:
        keyring.set_password(service, username, password)
    except Exception as e:
        raise DbError(f"keyring write failed: {e}") from e


def get_password(cfg: Config, *, prompt: bool = True) -> str | None:
    """Return the database password, or None if the backend doesn't need one.

    Order of resolution: skip if URL has no username (e.g. sqlite); else
    $CARTA_DB_PASSWORD, then keyring, then (if prompt=True) a getpass prompt
    validated against the database before being saved to the keyring.
    """
    url = _parsed_url(cfg)
    if not url.username:
        return None

    env = os.environ.get(PASSWORD_ENV)
    if env:
        return env

    try:
        stored = keyring.get_password(cfg.keyring_service, url.username)
    except Exception as e:
        raise DbError(f"keyring read failed: {e}") from e
    if stored:
        return str(stored)

    if not prompt:
        raise DbError(
            f"no password found in ${PASSWORD_ENV} or keyring "
            f"({cfg.keyring_service}:{url.username})"
        )

    password = getpass.getpass(f"Database password for {url.username}@{url.host or url.database}: ")
    _validate_with_connection(cfg, password)
    _save_password(cfg.keyring_service, url.username, password)
    return password


def reset_password(cfg: Config) -> str:
    """Delete the stored password and prompt for a fresh one."""
    url = _parsed_url(cfg)
    if not url.username:
        raise DbError("this DATABASE_URL has no username; nothing to reset")

    with contextlib.suppress(Exception):
        keyring.delete_password(cfg.keyring_service, url.username)
    password = getpass.getpass(
        f"New database password for {url.username}@{url.host or url.database}: "
    )
    _validate_with_connection(cfg, password)
    _save_password(cfg.keyring_service, url.username, password)
    return password


def _validate_with_connection(cfg: Config, password: str) -> None:
    try:
        conn = connect(cfg, password)
    except Exception as e:
        raise DbError(f"connection failed: {e}") from e
    conn.close()


def connect(cfg: Config, password: str | None = None) -> Connection:
    url = _parsed_url(cfg)
    if url.username and password is not None:
        url = url.set(password=password)
    engine = create_engine(url)
    return engine.connect()


def execute(conn: Connection, sql: str, params: dict[str, Any]) -> pl.DataFrame:
    """Run `sql` against `conn` with bound `params`, return a polars DataFrame.

    Callable values in `params` are invoked once here and the resolved value is
    bound. SQL uses `:name` placeholders regardless of backend.
    """
    bound = {name: (value() if callable(value) else value) for name, value in params.items()}
    result = conn.execute(text(sql), bound)
    if not result.returns_rows:
        return pl.DataFrame()
    return pl.DataFrame(result.mappings().all())
