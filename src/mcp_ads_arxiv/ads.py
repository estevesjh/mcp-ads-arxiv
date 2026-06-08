"""NASA ADS access: search, citation-graph traversal, and PDF link resolution.

Reuses the upstream mcp-server-ads ADSClient (HTTP, auth, rate-limit tracking, typed errors).
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from mcp_server_ads.client import ADSClient
from mcp_server_ads.config import ADS_API_URL

from . import cache

_SEARCH_FIELDS = "bibcode,title,abstract,keyword,year,author,identifier"
_RELATE_MODES = ("citations", "references", "similar")

_ARXIV_API = "https://export.arxiv.org/api/query"
_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}
# Bare arXiv id, with or without a version suffix: 2303.08774 / 2303.08774v2.
_ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


class ADSTokenMissing(RuntimeError):
    """Raised when ADS_API_TOKEN is not set."""


def is_arxiv_id(identifier: str) -> bool:
    """True if the string looks like a bare arXiv id (optionally 'arXiv:'-prefixed)."""
    s = identifier.strip()
    if s.lower().startswith("arxiv:"):
        s = s.split(":", 1)[1]
    return bool(_ARXIV_ID_RE.match(s))


def normalize_query(query: str) -> str:
    """Lift standalone year(s) into an ADS `year:` clause; otherwise pass through.

    Single year:    'Esteves 2023 tree rings' -> 'year:2023 Esteves tree rings'
    Year range:     'DES DESI 2025 2026 w0 wa' -> 'year:2025-2026 DES DESI w0 wa'
    Already fielded queries are returned unchanged.
    """
    if "year:" in query.lower():
        return query
    years = sorted(set(_YEAR_RE.findall(query)), key=lambda y: int("".join(y) if isinstance(y, tuple) else y))
    # _YEAR_RE has a group for the prefix (19|20); findall returns tuples. Reconstruct.
    year_strs = sorted(set(m.group(0) for m in _YEAR_RE.finditer(query)))
    if not year_strs:
        return query
    rest = _YEAR_RE.sub("", query).strip()
    rest = re.sub(r"\s{2,}", " ", rest)
    if len(year_strs) == 1:
        clause = f"year:{year_strs[0]}"
    else:
        clause = f"year:{min(year_strs)}-{max(year_strs)}"
    return f"{clause} {rest}".strip() if rest else clause


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
    rl = client.rate_limits
    cache.record_ads_call(limit=rl.limit, remaining=rl.remaining, reset=rl.reset)
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


def _strip_arxiv_id(raw: str) -> str:
    """'http://arxiv.org/abs/2303.08774v2' -> '2303.08774' (drop URL + version)."""
    tail = raw.rstrip("/").split("/")[-1]
    return re.sub(r"v\d+$", "", tail)


def _atom_to_papers(xml_text: str) -> list[dict[str, Any]]:
    """Parse an arXiv Atom feed into our normalized paper-dict shape (matches _docs_to_papers)."""
    import xml.etree.ElementTree as ET

    papers: list[dict[str, Any]] = []
    root = ET.fromstring(xml_text)
    for entry in root.findall("atom:entry", _ARXIV_NS):
        raw_id = (entry.findtext("atom:id", default="", namespaces=_ARXIV_NS) or "").strip()
        arxiv_id = _strip_arxiv_id(raw_id)
        title = (entry.findtext("atom:title", default="", namespaces=_ARXIV_NS) or "").strip()
        abstract = (entry.findtext("atom:summary", default="", namespaces=_ARXIV_NS) or "").strip()
        published = entry.findtext("atom:published", default="", namespaces=_ARXIV_NS) or ""
        year = int(published[:4]) if published[:4].isdigit() else None
        author_names = [
            (a.findtext("atom:name", default="", namespaces=_ARXIV_NS) or "").strip()
            for a in entry.findall("atom:author", _ARXIV_NS)
        ]
        doi = entry.findtext("arxiv:doi", default="",
                             namespaces={"arxiv": "http://arxiv.org/schemas/atom"}) or ""
        papers.append({
            "key": arxiv_id,
            "bibcode": "",
            "arxiv_id": arxiv_id,
            "doi": doi,
            "title": " ".join(title.split()),
            "abstract": " ".join(abstract.split()),
            "keywords": [],
            "authors": [n for n in author_names if n],
            "year": year,
        })
    return papers


async def arxiv_search(query: str, rows: int = 40) -> list[dict[str, Any]]:
    """Token-free search via the public arXiv API. Same paper-dict shape as `search`."""
    params = {"search_query": f"all:{query}", "start": 0, "max_results": rows}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(_ARXIV_API, params=params)
        resp.raise_for_status()
        return _atom_to_papers(resp.text)
