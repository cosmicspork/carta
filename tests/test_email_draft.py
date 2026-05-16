from __future__ import annotations

import email
from email import policy
from pathlib import Path

from carta.email_draft import XLSX_MIME_TYPE, write_eml


def _read(path: Path) -> email.message.EmailMessage:
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    assert isinstance(msg, email.message.EmailMessage)
    return msg


def test_writes_eml_with_headers_body_attachment(tmp_path: Path) -> None:
    xlsx = tmp_path / "report.xlsx"
    xlsx.write_bytes(b"PK\x03\x04fake-xlsx-bytes")
    out = tmp_path / "report.eml"

    write_eml(
        out,
        recipients=["a@x.com", "b@x.com"],
        cc=["c@x.com"],
        subject="Report — 2026-05-16",
        body_text="Hi there.\n\nThanks,",
        attachment_path=xlsx,
    )

    msg = _read(out)
    assert msg["To"] == "a@x.com, b@x.com"
    assert msg["Cc"] == "c@x.com"
    assert msg["Subject"] == "Report — 2026-05-16"
    assert msg["X-Unsent"] == "1"
    assert msg["Date"]
    assert msg.is_multipart()

    parts = list(msg.iter_parts())
    body_parts = [p for p in parts if p.get_content_disposition() != "attachment"]
    attach_parts = [p for p in parts if p.get_content_disposition() == "attachment"]
    assert len(body_parts) == 1
    assert "Hi there." in body_parts[0].get_content()
    assert len(attach_parts) == 1
    assert attach_parts[0].get_filename() == "report.xlsx"
    assert attach_parts[0].get_content_type() == XLSX_MIME_TYPE
    assert attach_parts[0].get_payload(decode=True) == b"PK\x03\x04fake-xlsx-bytes"


def test_no_cc_header_when_empty(tmp_path: Path) -> None:
    out = tmp_path / "x.eml"
    write_eml(
        out,
        recipients=["a@x.com"],
        cc=[],
        subject="S",
        body_text="B",
        attachment_path=None,
    )
    msg = _read(out)
    assert msg["Cc"] is None


def test_no_attachment(tmp_path: Path) -> None:
    out = tmp_path / "x.eml"
    write_eml(
        out,
        recipients=["a@x.com"],
        cc=[],
        subject="S",
        body_text="B",
        attachment_path=None,
    )
    msg = _read(out)
    # No attachment -> not multipart
    assert not msg.is_multipart()
    assert "B" in msg.get_content()
