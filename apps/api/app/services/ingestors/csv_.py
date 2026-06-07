"""CSV ingestor.

For user feedback / analytics exports / signup lists / etc.
Strategy: columns + types + row count + first 10 rows.
"""
from __future__ import annotations

import csv
import io
from typing import Optional

from .base import Ingestor, IngestResult, truncate_to_tokens


def _guess_type(value: str) -> str:
    if not value:
        return ""
    try:
        int(value)
        return "int"
    except ValueError:
        pass
    try:
        float(value)
        return "float"
    except ValueError:
        pass
    return "text"


class CsvIngestor(Ingestor):
    async def ingest(
        self,
        *,
        content: bytes,
        display_name: str,
        mime_type: Optional[str],
    ) -> IngestResult:
        try:
            text = content.decode("utf-8-sig")  # handle BOM
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")

        try:
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
        except Exception as e:
            return IngestResult(
                digest_md=f"# {display_name}\n\n_(CSV parse failed: {str(e)[:160]})_",
                error=str(e)[:300],
            )

        if not rows:
            return IngestResult(
                digest_md=f"# {display_name}\n\n_(empty CSV)_",
                metadata={"empty": True},
            )

        header_row = rows[0]
        data_rows = rows[1:]
        n_rows = len(data_rows)

        # Sample types from first 20 rows
        col_types: list[str] = []
        sample = data_rows[:20] if data_rows else []
        for col_idx in range(len(header_row)):
            seen: set[str] = set()
            for r in sample:
                if col_idx < len(r):
                    seen.add(_guess_type(r[col_idx]))
            seen.discard("")
            col_types.append(",".join(sorted(seen)) or "empty")

        sections: list[str] = [
            f"# {display_name}",
            "",
            f"_CSV · {n_rows:,} rows · {len(header_row)} columns_",
            "",
            "## Columns",
            "",
        ]
        for name, typ in zip(header_row, col_types, strict=False):
            sections.append(f"- `{name}` ({typ})")
        sections.append("")

        preview = data_rows[:10]
        if preview:
            sections.append("## First 10 rows\n")
            sections.append("| " + " | ".join(header_row) + " |")
            sections.append("|" + "|".join(["---"] * len(header_row)) + "|")
            for r in preview:
                # pad / truncate to header length
                cells = list(r) + [""] * (len(header_row) - len(r))
                cells = cells[: len(header_row)]
                # Escape pipes in cells
                cells = [(c or "").replace("|", "\\|") for c in cells]
                sections.append("| " + " | ".join(cells) + " |")
            sections.append("")

        body = truncate_to_tokens("\n".join(sections))
        return IngestResult(
            digest_md=body,
            metadata={
                "n_rows": n_rows,
                "n_columns": len(header_row),
                "column_names": header_row,
                "column_types": col_types,
            },
        )

    @classmethod
    def handles(cls, mime: Optional[str], name: str) -> bool:
        if mime in ("text/csv", "application/csv", "application/vnd.ms-excel"):
            return True
        return name.lower().endswith(".csv")
