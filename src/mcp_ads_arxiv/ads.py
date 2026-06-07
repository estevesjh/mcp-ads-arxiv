"""NASA ADS access: search, citation-graph traversal, and PDF link resolution.

Reuses the upstream mcp-server-ads ADSClient (HTTP, auth, rate-limit tracking, typed errors).
"""

from __future__ import annotations

from typing import Any

from mcp_server_ads.client import ADSClient
from mcp_server_ads.config import ADS_API_URL

_SEARCH_FIELDS = "bibcode,title,abstract,keyword,year,author,identifier"
_RELATE_MODES = ("citations", "references", "similar")


class ADSTokenMissing(RuntimeError):
    """Raised when ADS_API_TOKEN is not set."""


def _docs_to_papers(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize raw ADS docs into our paper dicts (key, bibcode, arxiv_id, doi, ...)."""
    papers: list[dict[str, Any]] = []
    for doc in docs:
        bibcode = doc.get("bibcode", "")
        arxiv_id = ""
        doi = ""
        for ident in doc.get("identifier", []):
            low = ident.lower()
            if low.startswith("arxiv:"):
                arxiv_id = ident.split(":", 1)[1]
            elif arxiv_id == "" and "/" not in ident and "." in ident and ident[0].isdigit():
                arxiv_id = ident  # bare arXiv id like 2303.08774
            elif ident.startswith("10.") and "/" in ident and not doi:
                doi = ident
        title = doc.get("title", [""])
        papers.append({
            "key": bibcode or arxiv_id or doi,
            "bibcode": bibcode,
            "arxiv_id": arxiv_id,
            "doi": doi,
            "title": title[0] if isinstance(title, list) else title,
            "abstract": doc.get("abstract", ""),
            "keywords": doc.get("keyword", []) or [],
            "authors": doc.get("author", []) or [],
            "year": int(doc["year"]) if doc.get("year") else None,
        })
    return papers


async def _query(q: str, rows: int) -> list[dict[str, Any]]:
    from mcp_server_ads.errors import ADSAuthError

    try:
        client = ADSClient.create()
    except ADSAuthError as exc:  # token missing or invalid at construction time
        raise ADSTokenMissing(str(exc)) from exc

    data = await client.get(
        "/v1/search/query",
        params={"q": q, "rows": rows, "fl": _SEARCH_FIELDS, "sort": "date desc"},
    )
    docs = data.get("response", {}).get("docs", [])
    return _docs_to_papers(docs)


async def search(query: str, rows: int = 40) -> list[dict[str, Any]]:
    """Free-text ADS search; returns normalized metadata-only paper dicts."""
    return await _query(query, rows)


async def related(bibcode: str, mode: str, topic: str | None = None,
                  rows: int = 40) -> list[dict[str, Any]]:
    """Citation-graph traversal.

    references -> the paper's own bibliography (backward; often a project's roots)
    citations  -> papers citing it (forward; impact / what came after)
    similar    -> topically adjacent papers
    `topic` ANDs a term to narrow the graph.
    """
    if mode not in _RELATE_MODES:
        raise ValueError(f"mode must be one of {_RELATE_MODES}, got {mode!r}")
    q = f"{mode}(bibcode:{bibcode})"
    if topic:
        q = f"{q} AND {topic}"
    return await _query(q, rows)


def pdf_urls(bibcode: str, arxiv_id: str | None = None) -> list[str]:
    """Candidate PDF URLs in preference order, used as a fallback when no arXiv .tex exists."""
    urls: list[str] = []
    if arxiv_id:
        urls.append(f"https://arxiv.org/pdf/{arxiv_id}")
    if bibcode:
        urls.append(f"{ADS_API_URL}/link_gateway/{bibcode}/EPRINT_PDF")
        urls.append(f"{ADS_API_URL}/link_gateway/{bibcode}/PUB_PDF")
    return urls
