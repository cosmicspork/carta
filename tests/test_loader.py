from pathlib import Path

from carta.loader import discover


def _write(p: Path, content: str) -> None:
    p.write_text(content)


def _good_py(key: str = "good") -> str:
    return (
        f'definition = {{"key": "{key}", "recipients": ["a@x.com"], '
        f'"subject": "S", "body": "B"}}\n'
    )


def test_discover_returns_valid_definition(tmp_path: Path) -> None:
    _write(tmp_path / "good.py", _good_py())
    _write(tmp_path / "good.sql", "SELECT 1 FROM dual\n")
    loaded, errors = discover(tmp_path)
    assert errors == []
    assert len(loaded) == 1
    assert loaded[0].key == "good"
    assert loaded[0].sql_text == "SELECT 1 FROM dual\n"
    assert loaded[0].source_path == tmp_path / "good.py"
    assert loaded[0].sql_path == tmp_path / "good.sql"


def test_discover_skips_underscore_prefixed_files(tmp_path: Path) -> None:
    _write(tmp_path / "_helpers.py", "x = 1\n")
    _write(tmp_path / "good.py", _good_py())
    _write(tmp_path / "good.sql", "SELECT 1 FROM dual\n")
    loaded, errors = discover(tmp_path)
    assert [d.source_path.name for d in loaded] == ["good.py"]
    assert errors == []


def test_discover_isolates_broken_file(tmp_path: Path) -> None:
    _write(tmp_path / "broken.py", "raise RuntimeError('boom')\n")
    _write(tmp_path / "good.py", _good_py())
    _write(tmp_path / "good.sql", "SELECT 1 FROM dual\n")
    loaded, errors = discover(tmp_path)
    assert [d.key for d in loaded] == ["good"]
    assert len(errors) == 1
    assert errors[0].source_path.name == "broken.py"
    assert "RuntimeError" in errors[0].message


def test_discover_reports_missing_definition_attr(tmp_path: Path) -> None:
    _write(tmp_path / "bare.py", "x = 1\n")
    loaded, errors = discover(tmp_path)
    assert loaded == []
    assert len(errors) == 1
    assert "missing top-level `definition`" in errors[0].message


def test_discover_reports_non_dict_definition(tmp_path: Path) -> None:
    _write(tmp_path / "bad.py", "definition = 42\n")
    loaded, errors = discover(tmp_path)
    assert loaded == []
    assert len(errors) == 1
    assert "must be a dict" in errors[0].message


def test_discover_reports_missing_sql_file(tmp_path: Path) -> None:
    _write(tmp_path / "good.py", _good_py())
    # no sibling .sql
    loaded, errors = discover(tmp_path)
    assert loaded == []
    assert len(errors) == 1
    assert "sibling SQL file not found" in errors[0].message


def test_discover_helpers_are_importable(tmp_path: Path) -> None:
    _write(tmp_path / "_helpers.py", "def term() -> str: return '202680'\n")
    _write(
        tmp_path / "good.py",
        "from _helpers import term\n"
        'definition = {"key": "good", "recipients": ["a@x.com"], '
        '"subject": "S", "body": "B", "params": {"term_code": term}}\n',
    )
    _write(tmp_path / "good.sql", "SELECT 1 FROM dual\n")
    loaded, errors = discover(tmp_path)
    assert errors == []
    assert callable(loaded[0].raw["params"]["term_code"])
    assert loaded[0].raw["params"]["term_code"]() == "202680"
