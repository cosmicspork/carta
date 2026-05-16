"""Write Outlook-ready .eml drafts with xlsx attached."""

from __future__ import annotations

from email.generator import BytesGenerator
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path

XLSX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_XLSX_MAIN, _XLSX_SUB = XLSX_MIME_TYPE.split("/", 1)


def write_eml(
    out_path: Path,
    *,
    recipients: list[str],
    cc: list[str],
    subject: str,
    body_text: str,
    attachment_path: Path | None,
) -> None:
    msg = EmailMessage()
    msg["To"] = ", ".join(recipients)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["X-Unsent"] = "1"  # Outlook draft marker
    msg.set_content(body_text)

    if attachment_path is not None:
        data = attachment_path.read_bytes()
        msg.add_attachment(
            data,
            maintype=_XLSX_MAIN,
            subtype=_XLSX_SUB,
            filename=attachment_path.name,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as fh:
        BytesGenerator(fh).flatten(msg)
