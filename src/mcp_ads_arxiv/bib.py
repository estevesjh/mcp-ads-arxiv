"""BibTeX library file (literature_review.bib) read/append + local search."""

from __future__ import annotations

import re
from typing import Any

import bibtexparser
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bwriter import BibTexWriter

from . import cache, config


def _load_db() -> BibDatabase:
    path = config.bib_path()
    if not path.exists():
        return BibDatabase()
    with path.open(encoding="utf-8") as fh:
        return bibtexparser.load(fh)


def existing_keys() -> set[str]:
    return {entry["ID"] for entry in _load_db().entries}


def append_entry(entry: dict[str, str]) -> None:
    """Append a BibTeX entry unless its ID already exists. Overleaf-friendly plain text."""
    db = _load_db()
    if any(e["ID"] == entry["ID"] for e in db.entries):
        return
    db.entries.append(entry)
    writer = BibTexWriter()
    writer.indent = "  "
    config.ensure_dirs()
    with config.bib_path().open("w", encoding="utf-8") as fh:
        fh.write(writer.write(db))


def make_entry(paper: dict[str, Any]) -> dict[str, str]:
    """Build a minimal BibTeX entry from a cached paper dict."""
    entry: dict[str, str] = {
        "ENTRYTYPE": "article",
        "ID": paper["key"],
    }
    if paper.get("title"):
        entry["title"] = str(paper["title"])
    authors = paper.get("authors") or []
    if authors:
        entry["author"] = " and ".join(authors)
    if paper.get("year"):
        entry["year"] = str(paper["year"])
    if paper.get("doi"):
        entry["doi"] = str(paper["doi"])
    if paper.get("arxiv_id"):
        entry["eprint"] = str(paper["arxiv_id"])
        entry["archivePrefix"] = "arXiv"
    if paper.get("bibcode"):
        entry["adsurl"] = f"https://ui.adsabs.harvard.edu/abs/{paper['bibcode']}"
    return entry


def search_local(query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Regex/substring search over the local library (SQLite index is the source of truth)."""
    # Validate the regex; fall back to plain substring if it is not valid.
    try:
        re.compile(query, re.IGNORECASE)
        use_regex = True
    except re.error:
        use_regex = False

    if not use_regex:
        return cache.search(query, limit=limit)

    rx = re.compile(query, re.IGNORECASE)
    hits: list[dict[str, Any]] = []
    for paper in cache.search("", limit=10_000):  # all rows, then regex-filter
        haystack = f"{paper.get('title', '')} {paper.get('abstract', '')}"
        if rx.search(haystack):
            hits.append(paper)
            if len(hits) >= limit:
                break
    return hits
