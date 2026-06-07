"""SQLite index over the local paper library.

One row per paper. `state` tracks how far acquisition got:
  metadata  - only ADS metadata known, nothing downloaded
  pdf_only  - PDF on disk but not yet converted
  md        - PDF converted to markdown (servable)
  tex       - arXiv LaTeX source on disk (preferred, servable)
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from . import config

STATES = ("metadata", "pdf_only", "md", "tex")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    key       TEXT PRIMARY KEY,
    bibcode   TEXT,
    arxiv_id  TEXT,
    doi       TEXT,
    title     TEXT,
    abstract  TEXT,
    keywords  TEXT,   -- json list
    authors   TEXT,   -- json list
    year      INTEGER,
    state     TEXT NOT NULL DEFAULT 'metadata',
    tex_path  TEXT,
    md_path   TEXT,
    pdf_path  TEXT
);
CREATE INDEX IF NOT EXISTS idx_papers_bibcode  ON papers(bibcode);
CREATE INDEX IF NOT EXISTS idx_papers_arxiv_id ON papers(arxiv_id);
"""

_LIST_FIELDS = {"keywords", "authors"}


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    config.ensure_dirs()
    conn = sqlite3.connect(config.db_path())
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for f in _LIST_FIELDS:
        d[f] = json.loads(d[f]) if d.get(f) else []
    return d


def get(key: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM papers WHERE key = ?", (key,)).fetchone()
        return _row_to_dict(row) if row else None


def find_by(bibcode: str | None = None, arxiv_id: str | None = None) -> dict[str, Any] | None:
    """Look up a paper by bibcode or arxiv_id (first match)."""
    with connect() as conn:
        if bibcode:
            row = conn.execute("SELECT * FROM papers WHERE bibcode = ?", (bibcode,)).fetchone()
            if row:
                return _row_to_dict(row)
        if arxiv_id:
            row = conn.execute(
                "SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)
            ).fetchone()
            if row:
                return _row_to_dict(row)
    return None


def upsert(paper: dict[str, Any]) -> None:
    """Insert or update a paper row. Unknown columns are ignored; list fields are json-encoded.

    For an existing row, only the provided non-None fields overwrite stored values, so a
    metadata-only sweep never clobbers a previously downloaded tex_path/state.
    """
    columns = (
        "key", "bibcode", "arxiv_id", "doi", "title", "abstract",
        "keywords", "authors", "year", "state", "tex_path", "md_path", "pdf_path",
    )
    incoming = {k: paper[k] for k in columns if k in paper}
    for f in _LIST_FIELDS:
        if f in incoming and incoming[f] is not None:
            incoming[f] = json.dumps(incoming[f])

    if "key" not in incoming:
        raise ValueError("upsert requires a 'key'")

    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM papers WHERE key = ?", (incoming["key"],)
        ).fetchone()
        if existing is None:
            cols = list(incoming)
            placeholders = ", ".join("?" for _ in cols)
            conn.execute(
                f"INSERT INTO papers ({', '.join(cols)}) VALUES ({placeholders})",
                [incoming[c] for c in cols],
            )
        else:
            updates = {k: v for k, v in incoming.items() if k != "key" and v is not None}
            if updates:
                assignments = ", ".join(f"{k} = ?" for k in updates)
                conn.execute(
                    f"UPDATE papers SET {assignments} WHERE key = ?",
                    [*updates.values(), incoming["key"]],
                )


def set_state(key: str, state: str, **paths: str) -> None:
    """Advance a paper's state and optionally record tex_path/md_path/pdf_path."""
    if state not in STATES:
        raise ValueError(f"invalid state {state!r}; expected one of {STATES}")
    allowed = {k: v for k, v in paths.items() if k in ("tex_path", "md_path", "pdf_path")}
    assignments = ", ".join(["state = ?", *[f"{k} = ?" for k in allowed]])
    with connect() as conn:
        conn.execute(
            f"UPDATE papers SET {assignments} WHERE key = ?",
            [state, *allowed.values(), key],
        )


def search(pattern: str, limit: int = 50) -> list[dict[str, Any]]:
    """Case-insensitive substring search over title + abstract."""
    like = f"%{pattern}%"
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM papers WHERE title LIKE ? OR abstract LIKE ? "
            "ORDER BY year DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
