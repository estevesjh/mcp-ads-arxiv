"""Filesystem layout for the local paper library, resolved from LIT_CACHE_DIR."""

from __future__ import annotations

import os
from pathlib import Path


def library_root() -> Path:
    """Root of the local library. LIT_CACHE_DIR if set, else the current working dir."""
    root = os.environ.get("LIT_CACHE_DIR")
    return Path(root).expanduser() if root else Path.cwd()


def bib_path() -> Path:
    return library_root() / "literature_review.bib"


def db_path() -> Path:
    return library_root() / ".lit_cache.db"


def library_dir() -> Path:
    return library_root() / "library"


def inbox_dir() -> Path:
    return library_root() / "inbox"


def paper_dir(key: str) -> Path:
    """Per-paper directory holding source.tex / paper.md / original.pdf."""
    return library_dir() / key


def ensure_dirs() -> None:
    """Create the library and inbox directories if missing."""
    library_dir().mkdir(parents=True, exist_ok=True)
    inbox_dir().mkdir(parents=True, exist_ok=True)
