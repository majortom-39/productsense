"""Code file ingestor.

Targets single source files (NOT whole repos — that's RepoIngestor's job).
Strategy:
  - Detect language from extension
  - Extract a structural skeleton: top-of-file comments, imports,
    top-level function/class names + signatures
  - Plus the first ~40 lines verbatim for orientation

Keeps Maya away from line-by-line code review (that's the coding agent's
job) while still giving her enough to reason about what the file IS.
"""
from __future__ import annotations

import re
from typing import Optional

from .base import Ingestor, IngestResult, truncate_to_tokens


# language → extension map (extension → human label)
_LANG_BY_EXT: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".js": "JavaScript",
    ".jsx": "JavaScript (React)",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ header",
    ".cs": "C#",
    ".sql": "SQL",
    ".sh": "Shell",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
}

# Crude language-agnostic patterns for top-level "things to surface"
_SYMBOL_PATTERNS = {
    "Python": [
        re.compile(r"^class\s+(\w+).*?:", re.MULTILINE),
        re.compile(r"^def\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE),
        re.compile(r"^async\s+def\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE),
    ],
    "TypeScript": [
        re.compile(r"^export\s+(?:async\s+)?function\s+(\w+)", re.MULTILINE),
        re.compile(r"^export\s+(?:abstract\s+)?class\s+(\w+)", re.MULTILINE),
        re.compile(r"^export\s+interface\s+(\w+)", re.MULTILINE),
        re.compile(r"^export\s+type\s+(\w+)", re.MULTILINE),
        re.compile(r"^export\s+const\s+(\w+)", re.MULTILINE),
    ],
}
_SYMBOL_PATTERNS["TypeScript (React)"] = _SYMBOL_PATTERNS["TypeScript"]
_SYMBOL_PATTERNS["JavaScript"] = _SYMBOL_PATTERNS["TypeScript"]
_SYMBOL_PATTERNS["JavaScript (React)"] = _SYMBOL_PATTERNS["TypeScript"]


def _lang_for(name: str) -> Optional[str]:
    lower = name.lower()
    for ext, label in _LANG_BY_EXT.items():
        if lower.endswith(ext):
            return label
    return None


def _extract_symbols(text: str, lang: str) -> list[str]:
    patterns = _SYMBOL_PATTERNS.get(lang, [])
    found: list[str] = []
    for p in patterns:
        for m in p.finditer(text):
            sig = m.group(0).strip().rstrip(":").rstrip(",")
            # Normalize whitespace
            sig = re.sub(r"\s+", " ", sig)
            if sig not in found:
                found.append(sig)
            if len(found) >= 40:
                break
    return found


class CodeIngestor(Ingestor):
    async def ingest(
        self,
        *,
        content: bytes,
        display_name: str,
        mime_type: Optional[str],
    ) -> IngestResult:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")

        lang = _lang_for(display_name) or "Unknown"
        lines = text.splitlines()
        n_lines = len(lines)
        symbols = _extract_symbols(text, lang)
        head = "\n".join(lines[:40])

        sections: list[str] = [
            f"# {display_name}",
            "",
            f"_Code file · {lang} · {n_lines:,} lines · {len(content):,} bytes_",
            "",
        ]
        if symbols:
            sections.append("## Top-level symbols\n")
            for s in symbols:
                sections.append(f"- `{s}`")
            sections.append("")
        sections.append("## File head (first 40 lines)\n")
        sections.append(f"```{lang.lower().split()[0] if lang != 'Unknown' else ''}".rstrip())
        sections.append(head)
        sections.append("```")

        body = truncate_to_tokens("\n".join(sections))
        return IngestResult(
            digest_md=body,
            metadata={
                "language": lang,
                "n_lines": n_lines,
                "n_symbols": len(symbols),
            },
        )

    @classmethod
    def handles(cls, mime: Optional[str], name: str) -> bool:
        return _lang_for(name) is not None
