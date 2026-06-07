from mcp_ads_arxiv import bib, cache, config


def test_make_entry_from_paper():
    entry = bib.make_entry({
        "key": "Doe2023",
        "title": "Dark matter review",
        "authors": ["Doe, J.", "Roe, R."],
        "year": 2023,
        "doi": "10.1000/xyz",
        "arxiv_id": "2303.08774",
        "bibcode": "2023arXiv230308774X",
    })
    assert entry["ID"] == "Doe2023"
    assert entry["author"] == "Doe, J. and Roe, R."
    assert entry["eprint"] == "2303.08774"
    assert entry["archivePrefix"] == "arXiv"
    assert "adsurl" in entry


def test_append_entry_is_idempotent():
    entry = {"ENTRYTYPE": "article", "ID": "Smith2020", "title": "X", "year": "2020"}
    bib.append_entry(entry)
    bib.append_entry(entry)  # second call must not duplicate
    assert bib.existing_keys() == {"Smith2020"}
    assert config.bib_path().exists()


def test_search_local_uses_cache():
    cache.upsert({"key": "a", "title": "Neutron star mergers", "year": 2021})
    cache.upsert({"key": "b", "title": "White dwarf cooling", "year": 2019})
    hits = bib.search_local("neutron")
    assert [h["key"] for h in hits] == ["a"]


def test_search_local_invalid_regex_falls_back_to_substring():
    cache.upsert({"key": "a", "title": "Galaxy (formation)", "year": 2021})
    # Unbalanced paren is an invalid regex; must not raise, falls back to substring.
    hits = bib.search_local("(formation")
    assert isinstance(hits, list)
