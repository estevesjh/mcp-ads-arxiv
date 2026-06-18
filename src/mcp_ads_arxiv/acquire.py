"""Acquisition spine: turn an identifier into a servable local copy.

Order of preference:
  1. arXiv LaTeX source  -> library/<key>/source.tex   (state=tex)
  2. PDF download        -> library/<key>/original.pdf  -> docling -> paper.md (state=md)
  3. Neither obtainable  -> ask the user to drop a PDF in inbox/  (state stays pdf_only/metadata)
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

from . import ads, cache, config, convert, progress


def _download(url: str, dest: Path, *, label: str) -> bool:
    """Stream a URL to dest with a stderr progress bar. Returns True on a PDF-looking 200."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as r:
            if r.status_code != 200:
                return False
            ctype = r.headers.get("content-type", "")
            if "pdf" not in ctype and not url.endswith("pdf") and "arxiv.org/pdf" not in url:
                # ADS link_gateway may redirect to an HTML paywall; skip non-PDF bodies.
                if "html" in ctype:
                    return False
            total = int(r.headers.get("content-length", 0))
            got = 0
            with dest.open("wb") as fh:
                for chunk in r.iter_bytes():
                    fh.write(chunk)
                    got += len(chunk)
                    progress.download_bar(got, total, label=label)
            progress.done(label)
        return dest.stat().st_size > 1024
    except httpx.HTTPError as exc:
        print(f"[acquire] download failed for {url}: {exc}", file=sys.stderr, flush=True)
        return False


def fetch_pdf(paper: dict, project_dir: str | None = None) -> dict:
    """Download a paper's PDF for human reading, even when .tex is already present.

    Stores library/<key>/original.pdf in the global library. Does NOT change the paper's state
    — Claude continues to serve the .tex/.md it was already serving. The PDF is for you.

    If a project dir is set/passed, also drops a symlink at <project_dir>/papers/<LastNameYear>.pdf
    so you can open it by author rather than by bibcode.
    """
    key = paper["key"]
    dest = config.paper_dir(key) / "original.pdf"
    config.ensure_dirs()
    downloaded = False
    if not (dest.exists() and dest.stat().st_size > 1024):
        arxiv_id = paper.get("arxiv_id") or None
        bibcode = paper.get("bibcode") or ""
        ok = False
        for url in ads.pdf_urls(bibcode, arxiv_id):
            if _download(url, dest, label=f"PDF {key}"):
                ok = True
                downloaded = True
                cache.upsert({"key": key, "pdf_path": str(dest)})
                break
        if not ok:
            return {
                "key": key,
                "error": (
                    f"Could not download a PDF for {key}. The paper may be closed-access. "
                    f"Drop the file into {config.inbox_dir()} and call ingest_inbox()."
                ),
            }

    result: dict = {"key": key, "pdf_path": str(dest), "downloaded": downloaded}

    papers_dir = config.project_papers_dir(project_dir)
    if papers_dir is not None:
        papers_dir.mkdir(parents=True, exist_ok=True)
        friendly = papers_dir / config.first_author_year_filename(paper, ext="pdf")
        if not friendly.exists() and not friendly.is_symlink():
            friendly.symlink_to(dest)
        result["project_pdf"] = str(friendly)
    return result


def fetch_tex(arxiv_id: str, key: str) -> Path | None:
    """Download + flatten arXiv LaTeX source into library/<key>/source.tex.

    Also copies image files (.eps/.pdf/.png/.jpg) to library/<key>/figures/
    and .bib/.bbl files to library/<key>/ for ARA compilation.
    """
    from arxiv_to_prompt import process_latex_source

    print(f"[acquire] arXiv LaTeX source for {arxiv_id} ...", file=sys.stderr, flush=True)
    try:
        latex = process_latex_source(arxiv_id)
    except Exception as exc:  # no source tarball, network error, etc.
        print(f"[acquire] no arXiv source ({exc})", file=sys.stderr, flush=True)
        return None
    if not latex or not latex.strip():
        return None
    out = config.paper_dir(key) / "source.tex"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(latex, encoding="utf-8")

    _copy_source_assets(arxiv_id, key)
    return out


def _copy_source_assets(arxiv_id: str, key: str) -> None:
    """Copy image and bib files from arxiv cache to library/<key>/."""
    import shutil

    from arxiv_to_prompt import process_latex_source

    try:
        figure_paths_raw = process_latex_source(arxiv_id, figure_paths_only=True, use_cache=True)
    except Exception:
        figure_paths_raw = None

    paper_d = config.paper_dir(key)
    image_exts = {".eps", ".pdf", ".png", ".jpg", ".jpeg", ".svg"}

    if figure_paths_raw:
        figures_dir = paper_d / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        for line in figure_paths_raw.strip().splitlines():
            p = Path(line.strip())
            if p.exists() and p.suffix.lower() in image_exts:
                dest = figures_dir / p.name
                if not dest.exists():
                    shutil.copy2(p, dest)

    # Also copy bib/bbl from the cache directory
    try:
        from arxiv_to_prompt import get_default_cache_dir
        base = get_default_cache_dir()
        # Try multiple naming patterns
        candidates = [
            base / arxiv_id,
            base / arxiv_id.replace("/", "_"),
        ]
        for cache_dir in candidates:
            if cache_dir.exists():
                for ext in ("*.bib", "*.bbl"):
                    for bib_file in cache_dir.glob(ext):
                        dest = paper_d / bib_file.name
                        if not dest.exists():
                            shutil.copy2(bib_file, dest)
                break
    except (ImportError, Exception):
        pass


def acquire(paper: dict) -> dict:
    """Acquire the best available copy for a cached paper dict. Returns a status dict."""
    config.ensure_dirs()
    key = paper["key"]
    arxiv_id = paper.get("arxiv_id") or None
    bibcode = paper.get("bibcode") or ""

    # 1. arXiv LaTeX source (preferred).
    if arxiv_id:
        tex = fetch_tex(arxiv_id, key)
        if tex:
            cache.set_state(key, "tex", tex_path=str(tex))
            return {"key": key, "state": "tex", "path": str(tex)}

    # 2. PDF fallback -> docling markdown.
    pdf_dest = config.paper_dir(key) / "original.pdf"
    for url in ads.pdf_urls(bibcode, arxiv_id):
        if _download(url, pdf_dest, label=f"PDF {key}"):
            cache.set_state(key, "pdf_only", pdf_path=str(pdf_dest))
            md = convert.pdf_to_markdown(pdf_dest, config.paper_dir(key) / "paper.md")
            cache.set_state(key, "md", md_path=str(md))
            return {"key": key, "state": "md", "path": str(md)}

    # 3. Manual fallback.
    return {
        "key": key,
        "state": paper.get("state", "metadata"),
        "needs_pdf": True,
        "message": (
            f"Could not auto-download a PDF for {key}. Drop the PDF into "
            f"{config.inbox_dir()} (any filename), then call ingest_inbox()."
        ),
    }


def ingest_inbox() -> list[dict]:
    """Convert every PDF in inbox/ to markdown and file it under library/<stem>/."""
    config.ensure_dirs()
    results: list[dict] = []
    for pdf in sorted(config.inbox_dir().glob("*.pdf")):
        key = pdf.stem
        dest_pdf = config.paper_dir(key) / "original.pdf"
        dest_pdf.parent.mkdir(parents=True, exist_ok=True)
        dest_pdf.write_bytes(pdf.read_bytes())
        cache.upsert({"key": key, "title": key, "state": "pdf_only", "pdf_path": str(dest_pdf)})
        md = convert.pdf_to_markdown(dest_pdf, config.paper_dir(key) / "paper.md")
        cache.set_state(key, "md", md_path=str(md))
        pdf.unlink()  # consumed from the inbox
        results.append({"key": key, "state": "md", "path": str(md)})
    return results
