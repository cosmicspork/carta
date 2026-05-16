"""Carta CLI entry point: load config, discover, validate, run."""

from __future__ import annotations

import argparse
import contextlib
import sys
from datetime import datetime

from sqlalchemy.engine.url import make_url

from carta import __version__, db, loader, runner, validator
from carta.config import Config, ConfigError, load_config


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    print(f"carta {__version__}")
    try:
        cfg = load_config()
    except ConfigError as e:
        print(f"ERROR: {e}")
        return 2

    print(f"  database:    {_redact(cfg.database_url)}")
    print(f"  definitions: {cfg.definitions_dir}")
    print(f"  output:      {cfg.output_dir}")
    print(f"  active:      {cfg.active or '(none)'}")
    print()

    if args.reset_password:
        try:
            db.reset_password(cfg)
        except db.DbError as e:
            print(f"ERROR: {e}")
            return 2
        print("Password updated.")
        return 0

    if not cfg.definitions_dir.is_dir():
        print(f"ERROR: definitions directory not found: {cfg.definitions_dir}")
        return 2

    return _run(cfg, args)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="carta")
    p.add_argument(
        "--only",
        default=None,
        help="Comma-separated subset of ACTIVE keys to run.",
    )
    p.add_argument(
        "--reset-password",
        action="store_true",
        help="Clear stored database password and prompt again.",
    )
    return p.parse_args(argv)


def _redact(url: str) -> str:
    """Hide the password if one was embedded in DATABASE_URL."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return url


def _run(cfg: Config, args: argparse.Namespace) -> int:
    loaded, load_errors = loader.discover(cfg.definitions_dir)
    for le in load_errors:
        print(f"[load] {le.source_path.name}: {le.message}")

    valid, validation_errors = validator.validate_all(loaded, cfg.active)
    for ve in validation_errors:
        print(f"[validate] {ve}")

    only = _parse_only(args.only) if args.only else None
    if only is not None:
        unknown = only - set(cfg.active)
        for k in sorted(unknown):
            print(f"[--only] {k!r} is not in ACTIVE; ignored.")
        active_keys = [k for k in cfg.active if k in only]
    else:
        active_keys = list(cfg.active)

    active_defs = [v for v in valid if v.key in active_keys]
    print(f"\nFound {len(loaded)} definition(s); {len(valid)} valid; {len(active_defs)} to run.")

    # Cross-definition conflicts (duplicate keys / filenames) and missing SQL
    # files abort before any query runs, so we don't half-deliver a batch.
    has_missing_sql = any("sibling SQL file not found" in le.message for le in load_errors)
    has_cross_def_conflict = any(
        ve.message.startswith("duplicate key ") or "also produced by" in ve.message
        for ve in validation_errors
    )
    if has_missing_sql or has_cross_def_conflict:
        print("\nAborting before run: fix the errors above and try again.")
        return 2

    if not active_defs:
        print("Nothing to run.")
        return 1 if (load_errors or validation_errors) else 0

    try:
        password = db.get_password(cfg)
        conn = db.connect(cfg, password)
    except Exception as e:
        print(f"\nERROR: could not connect to database: {e}")
        return 2

    ctx = runner.RunContext(out_dir=cfg.output_dir, run_dt=datetime.now())
    print(f"Writing to {ctx.run_dir}\n")
    try:
        results = runner.run_all(active_defs, conn, ctx)
    finally:
        with contextlib.suppress(Exception):
            conn.close()

    _print_summary(results)

    any_error = bool(load_errors or validation_errors) or any(r.status == "error" for r in results)
    return 1 if any_error else 0


def _parse_only(spec: str) -> set[str]:
    return {part.strip() for part in spec.split(",") if part.strip()}


def _print_summary(results: list[runner.RunResult]) -> None:
    print("Ingest results:")
    for r in results:
        if r.status == "ok":
            print(
                f"  ok    [{r.key}] {r.rows:,} rows -> {r.xlsx_name}, {r.eml_name}"
            )
        elif r.status == "skip":
            print(f"  skip  [{r.key}] 0 rows ({r.message})")
        else:
            print(f"  ERROR [{r.key}] {r.message}")


if __name__ == "__main__":
    sys.exit(main())
