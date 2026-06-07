"""Live integration tests against NASA ADS and arXiv.

Skipped unless ADS_API_TOKEN is set, so the default `uv run pytest` stays offline and fast.
Run with: ADS_API_TOKEN=... uv run pytest -m integration

Test papers (provided as real-world helpers, not dark-matter examples):
  ADS bibcode : 2010ApJ...720.1038B
  arXiv       : 1202.5242
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("ADS_API_TOKEN"),
    reason="ADS_API_TOKEN not set; skipping live ADS/arXiv integration tests",
)

BIBCODE = "2010ApJ...720.1038B"
ARXIV_ID = "1202.5242"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_returns_results():
    from mcp_ads_arxiv import ads

    papers = await ads.search("galaxy cluster mass", rows=3)
    assert papers
    assert all("bibcode" in p for p in papers)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_references_traversal():
    from mcp_ads_arxiv import ads

    refs = await ads.related(BIBCODE, mode="references", rows=5)
    assert isinstance(refs, list)


@pytest.mark.integration
def test_acquire_arxiv_tex():
    from mcp_ads_arxiv import acquire, cache

    cache.upsert({"key": ARXIV_ID, "arxiv_id": ARXIV_ID, "title": "live test paper"})
    result = acquire.acquire(cache.get(ARXIV_ID))
    assert result["state"] in ("tex", "md")
