"""mcp-ads-arxiv — a local astrophysics paper library MCP server.

Discovers papers via NASA ADS, acquires the best text form (arXiv LaTeX preferred, else
PDF->markdown via docling, else asks for a manual drop), and serves only lightweight text.
Claude never reads a raw PDF. Works with Claude Desktop and Claude Code over stdio.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from . import acquire as _acquire
from . import ads, bib, cache, config, survey

mcp = FastMCP("mcp-ads-arxiv")

_NO_TOKEN_MSG = (
    "ADS_API_TOKEN is not set. Get a free token at "
    "https://ui.adsabs.harvard.edu/user/settings/token and pass it to the server "
    "(e.g. `claude mcp add ... -e ADS_API_TOKEN=...`)."
)


@mcp.tool
def search_library(query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Search the LOCAL library first (free, no network). Regex or substring over titles and
    abstracts of papers already acquired. Returns hits with their acquisition `state`."""
    return bib.search_local(query, limit=limit)


@mcp.tool
async def search_ads(query: str, rows: int = 40) -> dict[str, Any]:
    """Search NASA ADS for papers (metadata only: title, abstract, keywords, authors, year).
    Caches results locally. Use AFTER search_library to fill gaps. Lightweight — no full text."""
    try:
        papers = await ads.search(query, rows=rows)
    except ads.ADSTokenMissing:
        return {"error": _NO_TOKEN_MSG, "papers": []}
    for p in papers:
        cache.upsert(p)
    return {"count": len(papers), "papers": papers}


@mcp.tool
async def related_papers(bibcode: str, mode: str = "references", topic: str | None = None,
                         rows: int = 40) -> dict[str, Any]:
    """Relate other works to a specific paper via the ADS citation graph.

    mode='references' -> the paper's own bibliography (backward; often the project's ROOTS).
    mode='citations'  -> papers that cite it (forward; impact / what came after).
    mode='similar'    -> topically adjacent papers.
    Optional `topic` narrows the graph (e.g. 'dark matter'). Metadata only; cached."""
    try:
        papers = await ads.related(bibcode, mode, topic=topic, rows=rows)
    except ads.ADSTokenMissing:
        return {"error": _NO_TOKEN_MSG, "papers": []}
    except ValueError as exc:
        return {"error": str(exc), "papers": []}
    for p in papers:
        cache.upsert(p)
    return {"count": len(papers), "mode": mode, "papers": papers}


@mcp.tool
def generate_dynamic_survey(papers: list[dict[str, Any]], n: int = 4) -> dict[str, Any]:
    """Pre-Flight Survey: cluster a set of paper metadata into 4 focus + 4 exclude topics.
    Present these to the user and WAIT for their choice before reading any full text."""
    return survey.generate(papers, n=n)


@mcp.tool
def get_paper(identifier: str) -> dict[str, Any]:
    """Acquire a paper into the local library. Resolves a cached identifier (bibcode / arXiv id
    / key), then tries arXiv LaTeX source first, falls back to PDF->markdown (docling), and if
    neither works asks you to drop a PDF in the inbox. NEVER reads a PDF raw. Run search_ads or
    search_library first so the paper's metadata is known."""
    paper = (
        cache.get(identifier)
        or cache.find_by(bibcode=identifier, arxiv_id=identifier)
    )
    if paper is None:
        return {
            "error": (
                f"Unknown identifier {identifier!r}. Run search_ads / search_library first so "
                "the paper's metadata is cached, then call get_paper with its key or bibcode."
            )
        }
    result = _acquire.acquire(paper)
    if result.get("state") in ("tex", "md"):
        bib.append_entry(bib.make_entry(paper))
    return result


@mcp.tool
def read_paper(identifier: str, sections: list[str] | None = None) -> dict[str, Any]:
    """Serve the stored text of an acquired paper (LaTeX source or docling markdown).
    Optionally pass `sections` (names) to return only those — the token-saving path. Call
    get_paper first if the paper is not yet acquired."""
    paper = cache.get(identifier) or cache.find_by(bibcode=identifier, arxiv_id=identifier)
    if paper is None:
        return {"error": f"{identifier!r} is not in the library. Call get_paper first."}

    state = paper.get("state")
    if state == "tex" and paper.get("tex_path"):
        from arxiv_to_prompt import extract_section, list_sections

        text = open(paper["tex_path"], encoding="utf-8").read()
        if not sections:
            return {"key": paper["key"], "format": "latex",
                    "sections_available": list_sections(text), "text": text}
        chosen = "\n\n".join(extract_section(text, s) or "" for s in sections)
        return {"key": paper["key"], "format": "latex", "sections": sections, "text": chosen}

    if state == "md" and paper.get("md_path"):
        text = open(paper["md_path"], encoding="utf-8").read()
        if sections:
            text = _slice_markdown(text, sections)
        return {"key": paper["key"], "format": "markdown", "sections": sections, "text": text}

    return {"error": f"{identifier!r} has no servable text yet (state={state}). Call get_paper."}


@mcp.tool
def ingest_inbox() -> dict[str, Any]:
    """Convert every PDF dropped in the inbox/ directory to markdown and file it into the
    library. Use after get_paper reported it could not auto-download a paper."""
    results = _acquire.ingest_inbox()
    return {"ingested": len(results), "papers": results}


def _slice_markdown(text: str, sections: list[str]) -> str:
    """Return only the markdown blocks whose heading matches one of `sections` (case-insensitive)."""
    wanted = [s.lower() for s in sections]
    out: list[str] = []
    keep = False
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            heading = line.lstrip("#").strip().lower()
            keep = any(w in heading for w in wanted)
        if keep:
            out.append(line)
    return "\n".join(out)


def main() -> None:
    config.ensure_dirs()
    mcp.run()


if __name__ == "__main__":
    main()
