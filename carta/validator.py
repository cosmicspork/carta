"""Validates definition contracts and runs cross-definition checks."""

from __future__ import annotations

import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from carta.loader import LoadedDefinition

NAME_PATTERN = r"^[a-z][a-z0-9_]*$"
_NAME_RE = re.compile(NAME_PATTERN)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SnakeCaseName = Annotated[str, Field(pattern=NAME_PATTERN)]

ALLOWED_PLACEHOLDERS = frozenset({"run_date", "run_datetime", "row_count", "key"})


def _check_template(value: str, *, field_name: str) -> str:
    try:
        parts = list(string.Formatter().parse(value))
    except ValueError as e:
        raise ValueError(f"{field_name}: invalid format string: {e}") from None
    for _literal, field, _spec, _conv in parts:
        if field is None:
            continue
        # `field` may be like "row_count" or "row_count[0]" or "x.y". Reject anything
        # that uses attribute/index access — placeholders are flat names only.
        root = field.split(".", 1)[0].split("[", 1)[0]
        if root not in ALLOWED_PLACEHOLDERS:
            allowed = ", ".join(f"{{{p}}}" for p in sorted(ALLOWED_PLACEHOLDERS))
            raise ValueError(
                f"{field_name}: unknown placeholder {{{field}}}; allowed: {allowed}"
            )
        if field != root:
            raise ValueError(
                f"{field_name}: placeholder {{{field}}} uses attribute/index access; "
                f"only flat names are supported"
            )
    return value


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    key: SnakeCaseName
    recipients: list[str] = Field(min_length=1)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)

    cc: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    filename: str = "{key}.xlsx"
    sheet_name: str = "Data"
    on_empty: Literal["skip", "send", "error"] = "skip"
    footer: bool = True

    @field_validator("recipients", "cc")
    @classmethod
    def _check_emails(cls, v: list[str]) -> list[str]:
        for addr in v:
            if not isinstance(addr, str) or not _EMAIL_RE.match(addr):
                raise ValueError(f"not a valid email address: {addr!r}")
        return v

    @field_validator("params")
    @classmethod
    def _check_params(cls, v: dict[str, Any]) -> dict[str, Any]:
        for name, value in v.items():
            if not isinstance(name, str) or not _NAME_RE.match(name):
                raise ValueError(f"param name {name!r} must match {NAME_PATTERN}")
            if value is None:
                continue
            if isinstance(value, str | int | float | bool):
                continue
            if callable(value):
                continue
            # Allow datetimes / dates / other oracledb-bindable scalars.
            if hasattr(value, "isoformat"):
                continue
            raise ValueError(
                f"param {name!r}: unsupported type {type(value).__name__}; "
                f"must be literal scalar, date/datetime, or zero-arg callable"
            )
        return v

    @model_validator(mode="after")
    def _check_templates(self) -> Definition:
        _check_template(self.subject, field_name="subject")
        _check_template(self.body, field_name="body")
        _check_template(self.filename, field_name="filename")
        if not self.filename.endswith(".xlsx"):
            raise ValueError("filename: must end in .xlsx")
        return self


def resolve_filename(template: str, key: str) -> str:
    """Resolve a filename template using a fixed sample mapping (cross-def collision check)."""
    return template.format(
        run_date="0000-00-00",
        run_datetime="0000-00-00 00:00",
        row_count=0,
        key=key,
    )


@dataclass(frozen=True)
class ValidationError:
    source_path: Path | None
    key: str | None
    message: str

    def __str__(self) -> str:
        loc = self.source_path.name if self.source_path else "<config>"
        tag = f"{loc}:{self.key}" if self.key else loc
        return f"[{tag}] {self.message}"


@dataclass(frozen=True)
class ValidatedDefinition:
    source_path: Path
    sql_path: Path
    sql_text: str
    definition: Definition

    @property
    def key(self) -> str:
        return self.definition.key


def validate_all(
    loaded: list[LoadedDefinition], active: list[str]
) -> tuple[list[ValidatedDefinition], list[ValidationError]]:
    """Validate every loaded definition; report cross-def collisions."""
    valid: list[ValidatedDefinition] = []
    errors: list[ValidationError] = []

    for d in loaded:
        result = _parse_one(d.source_path, d.raw)
        if isinstance(result, list):
            errors.extend(result)
        else:
            valid.append(
                ValidatedDefinition(
                    source_path=d.source_path,
                    sql_path=d.sql_path,
                    sql_text=d.sql_text,
                    definition=result,
                )
            )

    errors.extend(_cross_definition_checks(valid, active))
    return valid, errors


def _parse_one(source_path: Path, raw: dict[str, Any]) -> Definition | list[ValidationError]:
    raw_key = raw.get("key")
    key = raw_key if isinstance(raw_key, str) else None
    try:
        return Definition.model_validate(raw)
    except PydanticValidationError as exc:
        return _convert_pydantic_errors(exc, source_path, key)


def _convert_pydantic_errors(
    exc: PydanticValidationError, source_path: Path, key: str | None
) -> list[ValidationError]:
    out: list[ValidationError] = []
    for err in exc.errors():
        loc_parts = [str(p) for p in err["loc"] if p != "function-after"]
        loc = ".".join(loc_parts)
        msg = err["msg"].removeprefix("Value error, ")
        out.append(ValidationError(source_path, key, f"{loc}: {msg}" if loc else msg))
    return out


def _cross_definition_checks(
    valid: list[ValidatedDefinition], active: list[str]
) -> list[ValidationError]:
    errors: list[ValidationError] = []

    seen_keys: dict[str, Path] = {}
    for v in valid:
        if v.key in seen_keys:
            errors.append(
                ValidationError(
                    v.source_path,
                    v.key,
                    f"duplicate key {v.key!r}; first defined in {seen_keys[v.key].name}",
                )
            )
        else:
            seen_keys[v.key] = v.source_path

    active_set = set(active)
    filename_owner: dict[str, tuple[Path, str]] = {}
    for v in valid:
        if v.key not in active_set:
            continue
        resolved = resolve_filename(v.definition.filename, v.key)
        if resolved in filename_owner:
            prev_path, prev_key = filename_owner[resolved]
            errors.append(
                ValidationError(
                    v.source_path,
                    v.key,
                    f"filename {resolved!r} also produced by {prev_path.name}:{prev_key}",
                )
            )
        else:
            filename_owner[resolved] = (v.source_path, v.key)

    valid_keys = {v.key for v in valid}
    for k in active:
        if k not in valid_keys:
            errors.append(
                ValidationError(None, k, f"ACTIVE key {k!r} is not defined or failed validation")
            )

    return errors
