from __future__ import annotations

from pathlib import Path
from typing import Any

from carta.loader import LoadedDefinition
from carta.validator import validate_all


def _ld(name: str, raw: dict[str, Any]) -> LoadedDefinition:
    return LoadedDefinition(
        source_path=Path(f"definitions/{name}.py"),
        sql_path=Path(f"definitions/{name}.sql"),
        sql_text="SELECT 1 FROM dual",
        raw=raw,
    )


def _defn(key: str = "things", **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "key": key,
        "recipients": ["a@x.com"],
        "subject": "S {run_date}",
        "body": "Body {row_count}",
    }
    base.update(overrides)
    return base


def test_valid_minimum() -> None:
    valid, errors = validate_all([_ld("things", _defn())], active=["things"])
    assert errors == []
    assert len(valid) == 1
    assert valid[0].key == "things"
    assert valid[0].definition.cc == []
    assert valid[0].definition.on_empty == "skip"
    assert valid[0].definition.footer is True
    assert valid[0].definition.filename == "{key}.xlsx"
    assert valid[0].definition.sheet_name == "Data"


def test_key_must_be_snake_case() -> None:
    valid, errors = validate_all([_ld("x", _defn(key="BadName"))], active=[])
    assert valid == []
    assert any("key" in e.message for e in errors)


def test_recipients_must_be_non_empty() -> None:
    _, errors = validate_all([_ld("x", _defn(recipients=[]))], active=[])
    assert any("recipients" in e.message for e in errors)


def test_recipients_must_be_emails() -> None:
    _, errors = validate_all([_ld("x", _defn(recipients=["nope"]))], active=[])
    assert any("not a valid email" in e.message for e in errors)


def test_cc_validated_too() -> None:
    _, errors = validate_all([_ld("x", _defn(cc=["nope"]))], active=[])
    assert any("not a valid email" in e.message for e in errors)


def test_unknown_field_rejected() -> None:
    _, errors = validate_all([_ld("x", _defn(extra="nope"))], active=[])
    assert any("extra" in e.message.lower() or "forbidden" in e.message.lower() for e in errors)


def test_bad_placeholder_in_subject() -> None:
    _, errors = validate_all([_ld("x", _defn(subject="Hello {whoever}"))], active=[])
    assert any("unknown placeholder" in e.message for e in errors)


def test_attr_access_placeholder_rejected() -> None:
    _, errors = validate_all([_ld("x", _defn(body="row {row_count.imag}"))], active=[])
    assert any("attribute/index access" in e.message for e in errors)


def test_on_empty_must_be_known() -> None:
    _, errors = validate_all([_ld("x", _defn(on_empty="bogus"))], active=[])
    assert any("on_empty" in e.message for e in errors)


def test_filename_must_end_xlsx() -> None:
    _, errors = validate_all([_ld("x", _defn(filename="report.csv"))], active=[])
    assert any(".xlsx" in e.message for e in errors)


def test_params_accepts_callable_and_literals() -> None:
    def term() -> str:
        return "202680"

    valid, errors = validate_all(
        [_ld("x", _defn(params={"a": 1, "b": "two", "c": term}))], active=["things"]
    )
    assert errors == []
    assert valid[0].definition.params["c"]() == "202680"


def test_params_rejects_unsupported_type() -> None:
    _, errors = validate_all([_ld("x", _defn(params={"a": [1, 2, 3]}))], active=[])
    assert any("unsupported type" in e.message for e in errors)


def test_params_name_must_be_snake() -> None:
    _, errors = validate_all([_ld("x", _defn(params={"Bad-Name": 1}))], active=[])
    assert any("param name" in e.message for e in errors)


def test_duplicate_keys_across_files() -> None:
    _, errors = validate_all(
        [_ld("a", _defn(key="dup")), _ld("b", _defn(key="dup"))],
        active=["dup"],
    )
    assert any("duplicate key 'dup'" in e.message for e in errors)


def test_duplicate_resolved_filename_across_active() -> None:
    _, errors = validate_all(
        [
            _ld("a", _defn(key="alpha", filename="shared.xlsx")),
            _ld("b", _defn(key="beta", filename="shared.xlsx")),
        ],
        active=["alpha", "beta"],
    )
    assert any("also produced by" in e.message for e in errors)


def test_duplicate_filename_only_active_collide() -> None:
    _, errors = validate_all(
        [
            _ld("a", _defn(key="alpha", filename="shared.xlsx")),
            _ld("b", _defn(key="beta", filename="shared.xlsx")),
        ],
        active=["alpha"],  # only one active
    )
    assert not any("also produced by" in e.message for e in errors)


def test_active_key_missing_reported() -> None:
    _, errors = validate_all([_ld("a", _defn(key="alpha"))], active=["alpha", "ghost"])
    assert any("'ghost'" in e.message and "ACTIVE" in e.message for e in errors)
