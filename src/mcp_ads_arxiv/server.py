"""mcp-ads-arxiv — a local astrophysics paper library MCP server.

Discovers papers via NASA ADS, acquires the best text form (arXiv LaTeX preferred, else
PDF->markdown via docling, else asks for a manual drop), and serves only lightweight text.
Claude never reads a raw PDF. Works with Claude Desktop and Claude Code over stdio.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from . import acquire as _acquire
from . import ads, bib, cache, config, sections as _sections, survey, tokens
from .latexclean import clean_latex

mcp = FastMCP("mcp-ads-arxiv")

_NO_TOKEN_MSG = (
    "ADS_API_TOKEN is not set. Get a free token at "
    "https://ui.adsabs.harvard.edu/user/settings/token and pass it to the server "
    "(e.g. `claude mcp add ... -e ADS_API_TOKEN=...`)."
)


_ADS_NUDGE = (
    "Running in free arXiv-only mode. Set ADS_API_TOKEN to unlock citation graphs and "
    "metrics — https://ui.adsabs.harvard.edu/user/settings/token"
)


@mcp.tool
def search_library(query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Search the LOCAL library first (free, no network). Regex or substring over titles and
    abstracts of papers already acquired. Returns hits with their acquisition `state`."""
    return [cache.view(p) for p in bib.search_local(query, limit=limit)]


@mcp.tool
async def flexible_paper_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Human-friendly literature search. Accepts natural academic notation such as
    'Esteves 2023 tree rings', bare author names, or raw paper titles — no rigid syntax.

    Uses NASA ADS when ADS_API_TOKEN is set (best coverage + metadata). With no token it
    falls back to the free public arXiv API and appends a `tip` nudging you to add a key.
    Caches every hit locally. Lightweight — metadata only, author lists compressed, no
    full text. Feed >~10 hits into generate_dynamic_survey before reading any body."""
    try:
        papers = await ads.search(ads.normalize_query(query), rows=max_results)
        tip = None
    except ads.ADSTokenMissing:
        papers = await ads.arxiv_search(query, rows=max_results)
        tip = _ADS_NUDGE
    for p in papers:
        cache.upsert(p)
    result: dict[str, Any] = {
        "count": len(papers),
        "papers": [cache.view(p) for p in papers],
    }
    if tip:
        result["tip"] = tip
    return result


@mcp.tool
async def related_papers(bibcode: str, mode: str = "references", topic: str | None = None,
                         rows: int = 40) -> dict[str, Any]:
    """Citation-graph traversal via NASA ADS. PREFER THIS over reading the paper's `.tex`
    bibliography when the user asks about cited work — the result includes title + abstract +
    keywords for each match, so you can judge topical relevance directly.

    Use this tool whenever the question is "which references / citations of paper X are about
    Y?" — pass `topic="Y"` and ADS narrows the graph for you.

    mode='references' -> the paper's own bibliography (backward; foundations / methodology
                         roots). USE THIS for "citations relevant to its methodology /
                         halo model / sample selection / etc."
    mode='citations'  -> papers that cite this one (forward; impact / what came after).
    mode='similar'    -> topically adjacent papers (not directly linked in the graph).

    Returns metadata only — feed the result into generate_dynamic_survey for >~10 hits."""
    try:
        papers = await ads.related(bibcode, mode, topic=topic, rows=rows)
    except ads.ADSTokenMissing:
        return {"error": _NO_TOKEN_MSG, "papers": []}
    except ValueError as exc:
        return {"error": str(exc), "papers": []}
    for p in papers:
        cache.upsert(p)
    return {"count": len(papers), "mode": mode, "papers": [cache.view(p) for p in papers]}


@mcp.tool
def generate_dynamic_survey(papers: list[dict[str, Any]], n: int = 4) -> dict[str, Any]:
    """Pre-Flight Survey: cluster a set of paper metadata into 4 focus + 4 exclude topics.
    Present these to the user and WAIT for their choice before reading any full text."""
    return survey.generate(papers, n=n)


@mcp.tool
def set_project_dir(path: str | None = None) -> dict[str, Any]:
    """Pin a project directory for the rest of this server's lifetime. After this, smart_fetch_paper_content
    automatically symlinks each requested paper into <path>/papers/ as <bibcode>/ AND also
    downloads its PDF to <path>/papers/<FirstAuthorLastNameYear>.pdf for human reading.

    Pass the absolute path of your Claude Code session's working folder. Pass None or an empty
    string to clear. Project ./papers/ is just a shortcut view — sources stay in the global
    library so search_library remains powerful."""
    pinned = config.set_project_dir(path or None)
    return {"project_dir": str(pinned) if pinned else None}


def _resolve_for_fetch(identifier: str) -> tuple[dict[str, Any] | None, bool, str | None]:
    """Resolve an identifier to a paper dict ready for acquisition.

    Returns (paper, used_free_path, error). Routing mirrors the dual-entry flowchart:
      1. Already cached locally  -> use it (no network, no key needed).
      2. ADS token present       -> ads.search to map the identifier to a bibcode/arXiv id.
      3. No token, bare arXiv id  -> synthesize {key, arxiv_id} and stream .tex directly.
      4. No token, title/bibcode  -> arxiv_search to resolve to an arXiv id.
    """
    paper = cache.get(identifier) or cache.find_by(bibcode=identifier, arxiv_id=identifier)
    if paper is not None:
        return paper, False, None

    import asyncio

    # ADS premium path: resolve unknown identifier via a metadata search.
    try:
        hits = asyncio.run(ads.search(identifier, rows=1))
        if hits:
            cache.upsert(hits[0])
            return cache.get(hits[0]["key"]), False, None
    except ads.ADSTokenMissing:
        pass  # fall through to the free path

    # Free path: a bare arXiv id streams .tex with no search at all.
    if ads.is_arxiv_id(identifier):
        arxiv_id = identifier.split(":", 1)[1] if ":" in identifier else identifier
        import re as _re
        arxiv_id = _re.sub(r"v\d+$", "", arxiv_id)
        synth = {"key": arxiv_id, "arxiv_id": arxiv_id, "title": arxiv_id, "state": "metadata"}
        cache.upsert(synth)
        return cache.get(arxiv_id), True, None

    # Free path: resolve a title/bibcode through the public arXiv API.
    try:
        hits = asyncio.run(ads.arxiv_search(identifier, rows=1))
    except Exception as exc:  # network failure, malformed feed, etc.
        return None, True, f"arXiv lookup for {identifier!r} failed: {exc}"
    if hits:
        cache.upsert(hits[0])
        return cache.get(hits[0]["key"]), True, None

    return None, True, (
        f"Could not resolve {identifier!r} without an ADS key. Provide an explicit arXiv id "
        "(e.g. 2303.08774) or set ADS_API_TOKEN."
    )


@mcp.tool
def smart_fetch_paper_content(identifier: str, project_dir: str | None = None) -> dict[str, Any]:
    """Acquire a paper end-to-end in ONE call and report what's inside — WITHOUT dumping body
    text. Returns acquisition `state`, the section headings, the abstract, and a compressed
    author summary, which is everything you need to run the pre-flight survey. Read actual
    body text afterwards with read_topic / read_paper.

    Accepts a bibcode, an ADS key, OR a bare arXiv id (e.g. 2303.08774). Resolves the best
    text form internally: cached copy -> ADS (if a token is set) -> free arXiv API. Drops a
    <project_dir>/papers/<key>/ symlink and a human-readable PDF when a project_dir is active.
    NEVER reads a PDF raw."""
    paper, used_free, error = _resolve_for_fetch(identifier)
    if error:
        return {"error": error}
    assert paper is not None

    # Short-circuit: if the source is already cached on disk, skip the acquisition pipeline.
    state = paper.get("state")
    cached_path = paper.get("tex_path") if state == "tex" else paper.get("md_path") if state == "md" else None
    from pathlib import Path as _P
    if state in ("tex", "md") and cached_path and _P(cached_path).exists():
        result: dict[str, Any] = {
            "key": paper["key"], "state": state, "path": cached_path, "already_cached": True,
        }
    else:
        result = _acquire.acquire(paper)

    if result.get("state") in ("tex", "md"):
        bib.append_entry(bib.make_entry(paper))
        link = config.link_paper_into_project(paper["key"], project_dir)
        if link.get("link"):
            result["project_link"] = link["link"]
        # Also fetch the PDF for human reading and drop it next to the symlink.
        pdf = _acquire.fetch_pdf(cache.get(paper["key"]), project_dir=project_dir)
        if pdf.get("project_pdf"):
            result["project_pdf"] = pdf["project_pdf"]
        elif pdf.get("pdf_path"):
            result["pdf_path"] = pdf["pdf_path"]

        # Report what's inside (headings + abstract) so the survey can run without a 2nd call.
        fresh = cache.get(paper["key"]) or paper
        payload = _list_sections_payload(fresh)
        if payload:
            result.update(payload)
        shielded = cache.view(fresh)
        result["authors"] = shielded["authors"]
        result["author_count"] = shielded["author_count"]

    if used_free:
        result["tip"] = _ADS_NUDGE
    return result


def _list_sections_payload(paper: dict[str, Any]) -> dict[str, Any] | None:
    """Headings (+ abstract for LaTeX) of an acquired paper. None if no servable text yet.

    Shared by list_sections and smart_fetch_paper_content so both stay cheap and consistent.
    Measures only the abstract's token cost (headings are negligible).
    """
    state = paper.get("state")
    if state == "tex" and paper.get("tex_path"):
        from arxiv_to_prompt import extract_abstract, list_sections as _list_tex

        text = open(paper["tex_path"], encoding="utf-8").read()
        raw = _list_tex(text)
        abstract = clean_latex(extract_abstract(text) or "")
        result = {
            "format": "latex",
            "sections": [{"label": _sections.display_label(h), "raw": h} for h in raw],
            "abstract": abstract,
        }
        result.update(tokens.measure(abstract))
        return result

    if state == "md" and paper.get("md_path"):
        text = open(paper["md_path"], encoding="utf-8").read()
        raw = [
            line.lstrip("#").strip()
            for line in text.splitlines() if line.lstrip().startswith("#")
        ]
        result = {
            "format": "markdown",
            "sections": [{"label": h, "raw": h} for h in raw],
        }
        result.update(tokens.measure(""))
        return result

    return None


@mcp.tool
def list_sections(identifier: str) -> dict[str, Any]:
    """Return ONLY the section headings (and the abstract) of an acquired paper. CHEAP — a few
    hundred tokens, no body text. Use this to plan a targeted read_paper call: list headings
    first, pick the ones you need, then read_paper(sections=[...]). Never read full text just
    to discover what sections exist — that's a 10x-100x token waste."""
    paper = cache.get(identifier) or cache.find_by(bibcode=identifier, arxiv_id=identifier)
    if paper is None:
        return {"error": f"{identifier!r} is not in the library. Call smart_fetch_paper_content first."}

    payload = _list_sections_payload(paper)
    if payload is None:
        return {"error": f"{identifier!r} has no servable text yet (state={paper.get('state')}). "
                         "Call smart_fetch_paper_content."}
    return {"key": paper["key"], **payload}


@mcp.tool
def read_topic(identifier: str, topic: str) -> dict[str, Any]:
    """ONE-SHOT 'show me the X of paper Y'. Resolves a natural-language topic
    ('methodology', 'results', 'discussion', 'conclusions', 'introduction', 'abstract', or
    a free-text section name) to the matching section(s) and returns just that text.

    Use this whenever the user names a topic — it skips the list_sections round trip and
    keeps the call count low. Multiple matches are concatenated. If nothing matches, the
    tool reports the available section labels so you can ask the user for guidance instead
    of guessing."""
    paper = cache.get(identifier) or cache.find_by(bibcode=identifier, arxiv_id=identifier)
    if paper is None:
        return {"error": f"{identifier!r} is not in the library. Call smart_fetch_paper_content first."}

    state = paper.get("state")
    if state == "tex" and paper.get("tex_path"):
        from arxiv_to_prompt import extract_abstract, list_sections as _list_tex

        full_text = open(paper["tex_path"], encoding="utf-8").read()

        if topic.strip().lower() == "abstract":
            text = clean_latex(extract_abstract(full_text) or "")
            cost = tokens.measure(text, full_text=full_text)
            return {"key": paper["key"], "topic": topic, "matched_sections": ["abstract"],
                    "text": text, **cost}

        raw = _list_tex(full_text)
        hits = _sections.resolve_topic(topic, raw)
        if not hits:
            return {
                "key": paper["key"], "topic": topic, "matched_sections": [],
                "available_labels": [_sections.display_label(h) for h in raw],
                "hint": "no section matched; ask the user which label to use, or pass it "
                        "to read_paper(sections=[...]).",
            }
        chosen = clean_latex("\n\n".join(_sections.extract_by_raw_name(full_text, h) for h in hits))
        cost = tokens.measure(chosen, full_text=full_text)
        return {
            "key": paper["key"], "topic": topic,
            "matched_sections": [_sections.display_label(h) for h in hits],
            "text": chosen, **cost,
        }

    if state == "md" and paper.get("md_path"):
        full_text = open(paper["md_path"], encoding="utf-8").read()
        raw = [
            line.lstrip("#").strip()
            for line in full_text.splitlines() if line.lstrip().startswith("#")
        ]
        hits = _sections.resolve_topic(topic, raw)
        if not hits:
            return {
                "key": paper["key"], "topic": topic, "matched_sections": [],
                "available_labels": raw,
                "hint": "no section matched; ask the user which label to use.",
            }
        text = _slice_markdown(full_text, hits)
        cost = tokens.measure(text, full_text=full_text)
        return {"key": paper["key"], "topic": topic, "matched_sections": hits,
                "text": text, **cost}

    return {"error": f"{identifier!r} has no servable text yet (state={state}). Call smart_fetch_paper_content."}


@mcp.tool
def read_paper(identifier: str, sections: list[str] | None = None,
               full: bool = False) -> dict[str, Any]:
    """Serve the stored text of an acquired paper (LaTeX or docling markdown). The
    token-saving path is `sections=[...]`; pass `full=True` only when you actually need the
    whole body. With neither, this tool refuses and tells you to call list_sections first —
    full-paper reads cost 10k+ tokens and you almost never need them just to find a section."""
    paper = cache.get(identifier) or cache.find_by(bibcode=identifier, arxiv_id=identifier)
    if paper is None:
        return {"error": f"{identifier!r} is not in the library. Call smart_fetch_paper_content first."}

    if not sections and not full:
        return {
            "error": (
                "read_paper requires either sections=[...] or full=True. To discover headings "
                "first (cheap, no body text), call list_sections(identifier)."
            ),
            "key": paper.get("key"),
            "hint": "list_sections -> read_paper(sections=[chosen ones])",
        }

    state = paper.get("state")
    if state == "tex" and paper.get("tex_path"):
        from arxiv_to_prompt import list_sections as _list_tex

        full_text = open(paper["tex_path"], encoding="utf-8").read()
        if sections:
            raw_headings = _list_tex(full_text)
            resolved: list[str] = []
            unresolved: list[str] = []
            for s in sections:
                hit = _sections.resolve_section(s, raw_headings)
                if hit:
                    resolved.append(hit)
                else:
                    unresolved.append(s)
            chosen = clean_latex("\n\n".join(_sections.extract_by_raw_name(full_text, r) for r in resolved))
            cost = tokens.measure(chosen, full_text=full_text)
            return {
                "key": paper["key"], "format": "latex",
                "sections_requested": sections,
                "sections_resolved": [_sections.display_label(r) for r in resolved],
                "sections_unmatched": unresolved,
                "text": chosen, **cost,
            }
        cleaned = clean_latex(full_text)
        cost = tokens.measure(cleaned, full_text=full_text)
        return {"key": paper["key"], "format": "latex",
                "sections_available": _list_tex(full_text), "text": cleaned, **cost}

    if state == "md" and paper.get("md_path"):
        full_text = open(paper["md_path"], encoding="utf-8").read()
        text = _slice_markdown(full_text, sections) if sections else full_text
        cost = tokens.measure(text, full_text=full_text if sections else None)
        return {"key": paper["key"], "format": "markdown", "sections": sections,
                "text": text, **cost}

    return {"error": f"{identifier!r} has no servable text yet (state={state}). Call smart_fetch_paper_content."}


@mcp.tool
def library_status(project_dir: str | None = None) -> dict[str, Any]:
    """Report where the global library lives and what's symlinked into the project's papers/."""
    import os

    papers = config.project_papers_dir(project_dir)
    if papers and papers.exists():
        linked = sorted(p.name for p in papers.iterdir() if p.is_symlink() or p.is_dir())
    else:
        linked = []
    return {
        "global_library_root": str(config.library_root()),
        "lit_cache_dir_env": os.environ.get("LIT_CACHE_DIR"),
        "project_papers_dir": str(papers) if papers else None,
        "linked_in_project": linked,
        "linked_count": len(linked),
    }


@mcp.tool
def unlink_paper(key: str, project_dir: str | None = None) -> dict[str, Any]:
    """Remove a paper's project-side symlink. The paper stays in the global library."""
    return config.unlink_paper_from_project(key, project_dir)


@mcp.tool
def fetch_pdf(identifier: str, project_dir: str | None = None) -> dict[str, Any]:
    """Download the original PDF of an acquired paper for HUMAN reading (open it in a viewer).
    Stores the original under the global library AND, if a project_dir is set/passed, drops a
    <FirstAuthorLastNameYear>.pdf symlink in <project_dir>/papers/. Claude still serves the
    cached .tex/.md to itself — the PDF is not used as model input."""
    paper = cache.get(identifier) or cache.find_by(bibcode=identifier, arxiv_id=identifier)
    if paper is None:
        return {"error": f"{identifier!r} is not in the library. Call smart_fetch_paper_content first."}
    return _acquire.fetch_pdf(paper, project_dir=project_dir)


@mcp.tool
def ingest_inbox() -> dict[str, Any]:
    """Convert every PDF dropped in the inbox/ directory to markdown and file it into the
    library. Use after smart_fetch_paper_content reported it could not auto-download a paper."""
    results = _acquire.ingest_inbox()
    return {"ingested": len(results), "papers": results}


@mcp.tool
def usage_stats() -> dict[str, Any]:
    """Report cumulative usage for this library.

    `tokens_served` is the total tokens this server has handed to the model (a proxy for what
    Claude ingests from the library — the client's true billed total is not visible to an MCP
    server). `tokens_saved` is how much was avoided by serving sections instead of full papers.
    Also reports ADS API call count and the latest live ADS quota."""
    tu = cache.token_usage()
    au = cache.ads_usage()
    served = tu.get("tokens_served", 0)
    saved = tu.get("tokens_saved", 0)
    total_if_full = served + saved
    pct = round(100 * saved / total_if_full, 1) if total_if_full else 0.0
    return {
        "tokens_served": served,
        "tokens_saved": saved,
        "savings_pct": pct,
        "responses_measured": tu.get("response_count", 0),
        "ads_calls": au.get("call_count", 0),
        "ads_quota_remaining": au.get("last_remaining"),
        "ads_quota_limit": au.get("last_limit"),
        "note": "tokens_served is a proxy measured at the server; Claude's billed total is "
                "not observable from an MCP server.",
    }


def _slice_markdown(text: str, sections: list[str]) -> str:
    """Return only the markdown blocks whose heading fuzzily matches one of `sections`.

    Uses normalize_heading so 'methodology' matches '## Methodology and Models', etc.
    """
    wanted = [_sections.normalize_heading(s) for s in sections]
    out: list[str] = []
    keep = False
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            heading = _sections.normalize_heading(line.lstrip("#"))
            keep = any(w and (w in heading or heading in w) for w in wanted)
        if keep:
            out.append(line)
    return "\n".join(out)


def _warn_if_no_ads_key() -> None:
    """Print a one-time stderr notice when no ADS token is configured (free arXiv-only mode).

    stderr only — stdout is the JSON-RPC channel and must stay clean.
    """
    import sys

    from mcp_server_ads.client import ADSClient
    from mcp_server_ads.errors import ADSAuthError

    try:
        ADSClient.create()
    except ADSAuthError:
        print(
            "[mcp-ads-arxiv] No ADS_API_TOKEN found — running in FREE arXiv-only mode.\n"
            "  Discovery falls back to the public arXiv API; citation graphs/metrics are disabled.\n"
            "  Get a free token: https://ui.adsabs.harvard.edu/user/settings/token",
            file=sys.stderr, flush=True,
        )


def main() -> None:
    config.ensure_dirs()
    _warn_if_no_ads_key()
    mcp.run()


if __name__ == "__main__":
    main()
