"""Filesystem layout for the paper library.

A single GLOBAL library holds every fetched source (literature_review.bib, .lit_cache.db,
library/<key>/...). This keeps `search_library` powerful — one corpus, no fragmentation. The
global root is `LIT_CACHE_DIR` if set, else the current working directory.

A project folder gets a *view* of a subset of papers via `link_paper_into_project(key, dir)`,
which symlinks library/<key> from the global library into <project_dir>/papers/<key>. No data
is moved or duplicated. The project dir is whatever the caller passes (Claude can read its
session cwd and pass it explicitly), or whichever path was pinned by `set_project_dir()`.

An MCP server's own `Path.cwd()` is the path it was launched from (typically the repo via
`uv run --directory`), NOT the user's session cwd — so the project dir must be explicit.
"""

from __future__ import annotations

import os
from pathlib import Path

_pinned_project: Path | None = None


def library_root() -> Path:
    """The global library root."""
    env = os.environ.get("LIT_CACHE_DIR")
    if env:
        return Path(env).expanduser()
    return Path.cwd()


def set_project_dir(path: str | None) -> Path | None:
    """Pin a project directory for the rest of this server process. Pass None to clear."""
    global _pinned_project
    _pinned_project = Path(path).expanduser().resolve() if path else None
    return _pinned_project


def resolve_project_dir(explicit: str | None) -> Path | None:
    """Resolve the active project dir: explicit arg wins, else the pinned value."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    return _pinned_project


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


def project_papers_dir(project_dir: str | None = None) -> Path | None:
    """Where this project's symlinks to global papers live (<project_dir>/papers/).
    Returns None if no project dir was set or passed."""
    pd = resolve_project_dir(project_dir)
    return pd / "papers" if pd else None


def ensure_dirs() -> None:
    """Create the global library and inbox directories if missing."""
    library_dir().mkdir(parents=True, exist_ok=True)
    inbox_dir().mkdir(parents=True, exist_ok=True)


def link_paper_into_project(key: str, project_dir: str | None = None) -> dict[str, object]:
    """Create <project_dir>/papers/<key> as a symlink to the global library/<key> directory.

    Idempotent. Returns the symlink path or an error if the source paper doesn't exist in the
    global library yet, or if no project dir was set / passed.
    """
    src = paper_dir(key)
    if not src.exists():
        return {"error": f"{key!r} is not in the global library yet. Call get_paper first."}
    dest_dir = project_papers_dir(project_dir)
    if dest_dir is None:
        return {"key": key, "linked": False,
                "note": "no project_dir set; pass project_dir or call set_project_dir first."}
    dest_dir.mkdir(parents=True, exist_ok=True)
    link = dest_dir / key
    if link.is_symlink() or link.exists():
        return {"key": key, "link": str(link), "created": False}
    link.symlink_to(src)
    return {"key": key, "link": str(link), "target": str(src), "created": True}


def unlink_paper_from_project(key: str, project_dir: str | None = None) -> dict[str, object]:
    """Remove a project symlink. The paper itself stays in the global library."""
    dest_dir = project_papers_dir(project_dir)
    if dest_dir is None:
        return {"key": key, "removed": False, "note": "no project_dir set."}
    link = dest_dir / key
    if link.is_symlink():
        link.unlink()
        return {"key": key, "removed": True}
    return {"key": key, "removed": False}


def first_author_year_filename(paper: dict, ext: str = "pdf") -> str:
    """Build a 'LastNameYYYY.<ext>' filename for human reading. Falls back to the paper key."""
    authors = paper.get("authors") or []
    year = paper.get("year") or ""
    last = ""
    if authors:
        # ADS authors are "Last, First" — take the first author's lastname.
        first_author = str(authors[0])
        last = first_author.split(",")[0].strip().replace(" ", "")
    if not last:
        last = paper.get("key", "paper").split(".")[0]  # bibcode prefix as last resort
    if not year:
        year = paper.get("key", "")[:4] if paper.get("key", "")[:4].isdigit() else ""
    base = f"{last}{year}" if year else last
    return f"{base}.{ext}"
