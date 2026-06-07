from mcp_ads_arxiv import cache


def test_upsert_and_get_roundtrip():
    cache.upsert({
        "key": "2012arXiv1202.5242B",
        "bibcode": "2012arXiv1202.5242B",
        "arxiv_id": "1202.5242",
        "title": "Galaxy cluster mass measurements",
        "abstract": "We measure cluster masses via weak gravitational lensing.",
        "keywords": ["galaxy clusters", "weak lensing"],
        "authors": ["Becker, M.", "Kravtsov, A."],
        "year": 2012,
    })
    p = cache.get("2012arXiv1202.5242B")
    assert p is not None
    assert p["arxiv_id"] == "1202.5242"
    assert p["keywords"] == ["galaxy clusters", "weak lensing"]
    assert p["authors"] == ["Becker, M.", "Kravtsov, A."]
    assert p["state"] == "metadata"


def test_find_by_bibcode_and_arxiv():
    cache.upsert({"key": "k1", "bibcode": "BIB1", "arxiv_id": "1111.2222"})
    assert cache.find_by(bibcode="BIB1")["key"] == "k1"
    assert cache.find_by(arxiv_id="1111.2222")["key"] == "k1"
    assert cache.find_by(bibcode="NOPE") is None


def test_set_state_advances_and_records_paths():
    cache.upsert({"key": "k2", "title": "t"})
    cache.set_state("k2", "tex", tex_path="/lib/k2/source.tex")
    p = cache.get("k2")
    assert p["state"] == "tex"
    assert p["tex_path"] == "/lib/k2/source.tex"


def test_metadata_sweep_does_not_clobber_downloaded_state():
    cache.upsert({"key": "k3", "title": "t"})
    cache.set_state("k3", "tex", tex_path="/lib/k3/source.tex")
    # A later metadata-only sweep (no state, no tex_path) must not wipe the download.
    cache.upsert({"key": "k3", "abstract": "fresh abstract"})
    p = cache.get("k3")
    assert p["state"] == "tex"
    assert p["tex_path"] == "/lib/k3/source.tex"
    assert p["abstract"] == "fresh abstract"


def test_search_substring():
    cache.upsert({"key": "a", "title": "Dark matter halos", "year": 2020})
    cache.upsert({"key": "b", "title": "Galaxy rotation curves", "year": 2021})
    hits = cache.search("dark")
    assert [h["key"] for h in hits] == ["a"]
