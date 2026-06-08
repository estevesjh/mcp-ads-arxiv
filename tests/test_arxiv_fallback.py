import pytest

from mcp_ads_arxiv import ads


def test_is_arxiv_id():
    assert ads.is_arxiv_id("2303.08774")
    assert ads.is_arxiv_id("2303.08774v2")
    assert ads.is_arxiv_id("arXiv:2303.08774")
    assert not ads.is_arxiv_id("Esteves 2023 tree rings")
    assert not ads.is_arxiv_id("2012arXiv1202.5242B")


def test_normalize_query_lifts_year():
    assert ads.normalize_query("Esteves 2023 tree rings") == "year:2023 Esteves tree rings"


def test_normalize_query_passthrough_without_year():
    assert ads.normalize_query("dark matter halos") == "dark matter halos"


def test_normalize_query_skips_already_fielded():
    q = "year:2020 lensing"
    assert ads.normalize_query(q) == q


def test_strip_arxiv_id():
    assert ads._strip_arxiv_id("http://arxiv.org/abs/2303.08774v2") == "2303.08774"
    assert ads._strip_arxiv_id("2303.08774") == "2303.08774"


def test_atom_parsing_shape():
    xml = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2010.00619v1</id>
        <title>A Test Paper</title>
        <summary>An abstract with   extra   spaces.</summary>
        <published>2020-10-01T00:00:00Z</published>
        <author><name>Doe, J.</name></author>
        <author><name>Roe, R.</name></author>
      </entry>
    </feed>"""
    papers = ads._atom_to_papers(xml)
    assert len(papers) == 1
    p = papers[0]
    assert p["arxiv_id"] == "2010.00619"
    assert p["key"] == "2010.00619"
    assert p["title"] == "A Test Paper"
    assert p["abstract"] == "An abstract with extra spaces."
    assert p["year"] == 2020
    assert p["authors"] == ["Doe, J.", "Roe, R."]


@pytest.mark.integration
def test_arxiv_search_live():
    import asyncio
    papers = asyncio.run(ads.arxiv_search("galaxy cluster lensing", rows=2))
    assert papers
    assert all(p["arxiv_id"] for p in papers)
