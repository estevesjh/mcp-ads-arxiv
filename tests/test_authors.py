from mcp_ads_arxiv import authors, cache


def test_short_list_unchanged():
    names = ["Becker, M.", "Kravtsov, A."]
    assert authors.compress(names) == names


def test_empty_list():
    assert authors.compress([]) == []


def test_long_list_collapses_with_count(monkeypatch):
    monkeypatch.delenv("AUTHOR_DISPLAY_MAX", raising=False)
    names = [f"Author{i}, X." for i in range(2340)]
    out = authors.compress(names)
    assert isinstance(out, str)
    assert out.startswith("Author0, X.; Author1, X.; Author2, X. et al.")
    assert "(2,340 authors)" in out


def test_at_threshold_not_collapsed(monkeypatch):
    monkeypatch.delenv("AUTHOR_DISPLAY_MAX", raising=False)
    names = [f"A{i}" for i in range(10)]  # exactly DEFAULT_MAX
    assert authors.compress(names) == names


def test_env_override(monkeypatch):
    monkeypatch.setenv("AUTHOR_DISPLAY_MAX", "2")
    out = authors.compress(["A, a", "B, b", "C, c"])
    assert isinstance(out, str)
    assert "(3 authors)" in out


def test_view_shields_authors(monkeypatch):
    monkeypatch.setenv("AUTHOR_DISPLAY_MAX", "3")
    big = [f"Name{i}" for i in range(50)]
    cache.upsert({"key": "kbig", "title": "t", "authors": big, "tex_path": "/secret/path"})
    v = cache.view(cache.get("kbig"))
    assert isinstance(v["authors"], str)
    assert v["author_count"] == 50
    # The shield must not leak raw file paths to the model.
    assert "tex_path" not in v
    assert "md_path" not in v
