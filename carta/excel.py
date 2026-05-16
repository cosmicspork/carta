"""DataFrame -> xlsx file (single sheet, frozen header, autofit columns)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import xlsxwriter

MAX_COL_WIDTH = 50


def write_xlsx(df: pl.DataFrame, out_path: Path, sheet_name: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with xlsxwriter.Workbook(str(out_path)) as wb:
        ws = wb.add_worksheet(sheet_name)
        header_fmt = wb.add_format({"bold": True})

        columns = df.columns
        max_lens = [len(name) for name in columns]
        for col_idx, name in enumerate(columns):
            ws.write(0, col_idx, name, header_fmt)

        for row_idx, row in enumerate(df.iter_rows(), start=1):
            for col_idx, value in enumerate(row):
                cell = _to_cell(value)
                ws.write(row_idx, col_idx, cell)
                if max_lens[col_idx] >= MAX_COL_WIDTH:
                    continue
                s = cell if isinstance(cell, str) else str(cell)
                if len(s) > max_lens[col_idx]:
                    max_lens[col_idx] = len(s)

        if columns:
            ws.freeze_panes(1, 0)

        for col_idx, longest in enumerate(max_lens):
            ws.set_column(col_idx, col_idx, float(min(MAX_COL_WIDTH, longest + 2)))


def _to_cell(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, str | int | float | bool):
        return value
    return str(value)
