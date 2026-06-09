"""PDF -> markdown conversion via docling.

IRON RULE: Claude never reads a raw PDF. This module is the only path from a PDF to text,
and it always produces markdown. docling is imported lazily because its model load is heavy;
that cost is paid once per process, off the read hot path.
"""

from __future__ import annotations

import sys
from pathlib import Path


def pdf_to_markdown(pdf_path: Path, out_path: Path) -> Path:
    """Convert a local PDF to markdown and write it to out_path. Returns out_path."""
    print(f"[convert] docling: {pdf_path.name} -> markdown ...", file=sys.stderr, flush=True)
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        raise RuntimeError(
            "docling is not installed. Install it with: pip install 'mcp-ads-arxiv[pdf]'\n"
            "Without docling, only papers with arXiv LaTeX source can be acquired."
        )

    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    markdown = result.document.export_to_markdown()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    print(f"[convert] wrote {out_path}", file=sys.stderr, flush=True)
    return out_path
