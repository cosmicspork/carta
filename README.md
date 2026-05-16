# Carta

A local automation tool that runs SQL queries on a schedule, produces xlsx workbooks, and saves Outlook-ready `.eml` drafts the analyst opens, reviews, and sends.

Built on the same patterns as [mesa](../mesa): one Python file per report, pydantic-validated contract, auto-discovery, per-definition error isolation.

The authoritative reference is `SPEC.md` in the parent directory.

## Why this exists

The manual loop is: run a query in the GUI, save xlsx, paste into Outlook, fix the subject, attach, send. Doing this once a week works. Doing it for ten reports twice a week doesn't.

Carta automates the middle. Drop a Python file per report into `definitions/` with a sibling `.sql` next to it, double-click `run.bat`, and Carta produces a folder of ready-to-send `.eml` files with the xlsx already attached. The analyst opens each draft in Outlook, reviews it, and hits Send.

The tool deliberately stops short of sending.

## Install

Requires [uv](https://github.com/astral-sh/uv) and Python 3.13.

```bash
uv sync --extra dev --extra oracle      # or --extra postgres, --extra mysql, --extra mssql
```

SQLite needs no extra (built into Python). Pick whichever driver matches your `DATABASE_URL`.

## Run

```bash
uv run carta                                    # run all ACTIVE definitions
uv run carta --only enrollment_by_term          # run a subset
uv run carta --reset-password                   # clear and re-prompt
uv run pytest                                   # tests
uv run ruff check .                             # lint
uv run mypy carta                               # type check
```

The `run.bat` (Windows) and `run.sh` (Unix) wrappers exist for double-click runs without opening a terminal.

First run prompts for the database password, validates it by opening a connection, and stores it in the OS credential store (`keyring`). Subsequent runs read silently. Set `CARTA_DB_PASSWORD` in the environment to bypass the keyring entirely. Backends with no user in the URL (sqlite) skip the password layer.

## Database support

One database per project — change `DATABASE_URL` to switch. SQL files use `:name` named parameters regardless of backend; SQLAlchemy translates to each driver's native binding.

| Backend | `DATABASE_URL` example | Install extra |
|---|---|---|
| Oracle | `oracle+oracledb://user@host:1521/?service_name=PROD` | `--extra oracle` |
| PostgreSQL | `postgresql+psycopg://user@host:5432/dbname` | `--extra postgres` |
| MySQL | `mysql+pymysql://user@host:3306/dbname` | `--extra mysql` |
| SQL Server | `mssql+pyodbc://user@host:1433/dbname?driver=ODBC+Driver+18+for+SQL+Server` | `--extra mssql` |
| SQLite | `sqlite:///path/to/local.sqlite` | (built in) |

## What you'll edit

| File / folder | Purpose |
|---|---|
| `config.py` | `DATABASE_URL`, keyring service name, `ACTIVE` list, output dir |
| `definitions/*.py` | One file per report |
| `definitions/*.sql` | The SQL for each report, same stem as the `.py` |
| `run.bat` / `run.sh` | Double-click to run |

`definitions/` is gitignored except for `.gitignore` itself — real reports never get committed.

## Architecture

- `carta/` — framework. Auto-discovers `definitions/*.py`, validates each (pydantic), runs queries, builds xlsx + `.eml` drafts.
- `definitions/` — one `.py` per report plus a sibling `.sql` with the same stem. Files starting with `_` are skipped by discovery but importable as modules (use them for shared helpers).
- `config.py` — connection URL, keyring service name, active list, output dir.

Each run produces a fresh timestamped folder under `out/`. There is no state between runs other than what lands on disk.

## The Definition Contract

Each `definitions/*.py` exposes a single top-level `definition` dict, paired with a sibling `.sql` file of the same stem.

```python
# definitions/enrollment_by_term.py
from _helpers import current_term_code

definition = {
    "key": "enrollment_by_term",
    "recipients": ["registrar@uni.edu", "dean@uni.edu"],
    "cc": [],
    "subject": "Enrollment by Term — {run_date}",
    "body": (
        "Hi all,\n\n"
        "Attached is the enrollment-by-term report for {run_date} "
        "({row_count:,} rows).\n\n"
        "Thanks,"
    ),
    "params": {"term_code": current_term_code},
}
```

```sql
-- definitions/enrollment_by_term.sql
SELECT student_id, program_code, credits
FROM   enrollment
WHERE  term_code = :term_code
```

### Required fields

| Field | Type | Notes |
|---|---|---|
| `key` | `str` (snake_case) | Used for filenames and the run summary |
| `recipients` | `list[str]` | At least one email address |
| `subject` | `str` | Supports `{run_date}`, `{run_datetime}`, `{row_count}`, `{key}` |
| `body` | `str` | Same placeholders as `subject` |

### Optional fields

| Field | Type | Default | Notes |
|---|---|---|---|
| `cc` | `list[str]` | `[]` | |
| `params` | `dict[str, value or callable]` | `{}` | Bind to `:name` in the SQL |
| `filename` | `str` | `"{key}.xlsx"` | Supports same placeholders |
| `sheet_name` | `str` | `"Data"` | xlsx sheet name |
| `on_empty` | `"skip" \| "send" \| "error"` | `"skip"` | What to do when the query returns 0 rows |
| `footer` | `bool` | `True` | Append generation metadata to body |

Unknown fields are rejected.

## config.py

```python
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

DEFINITIONS_DIR = REPO_ROOT / "definitions"
OUTPUT_DIR      = REPO_ROOT / "out"

DATABASE_URL    = "oracle+oracledb://analyst_readonly@oradb.uni.edu:1521/?service_name=PROD"
KEYRING_SERVICE = "carta_db"

ACTIVE: list[str] = [
    "enrollment_by_term",
]
```

## Errors and exit codes

Carta isolates failures so one bad definition doesn't stop the rest.

- **Load error** (broken Python file) — reported, file skipped, others continue.
- **Validation error** — reported, definition excluded, others continue.
- **Cross-definition conflict** (duplicate `key`, or two active definitions whose `filename` would resolve to the same value) — aborts before any query runs.
- **Missing SQL file** — all missing files reported up front; aborts before any query runs.
- **Connection failure** — aborts before any query runs.
- **Per-definition runtime error** — reported with traceback; that definition produces no output, others continue.

| Exit code | Meaning |
|---|---|
| 0 | All active definitions produced drafts cleanly |
| 1 | Ran, but at least one load / validation / query / render error |
| 2 | Aborted before run (config invalid, connection failed, SQL files missing, cross-def conflict) |

## Non-goals

See `SPEC.md` for the authoritative non-goals list. Highlights: no auto-send, no SMTP, no HTML email, no multiple databases per run, no CLI parameter overrides, no incremental modes.
