"""Tests for the ARA compilation module (unit-level, no SDK calls)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_ads_arxiv import ara, cache, config


@pytest.fixture
def tmp_library(tmp_path, monkeypatch):
    """Point the library at a temp directory."""
    monkeypatch.setenv("LIT_CACHE_DIR", str(tmp_path))
    lib = cache.Library(tmp_path / ".lit_cache.db")
    with patch.object(cache, "_default", lib):
        yield tmp_path


@pytest.fixture
def paper_with_tex(tmp_library):
    """Create a minimal paper entry with a .tex file."""
    key = "2024TestPaper"
    paper_dir = tmp_library / "library" / key
    paper_dir.mkdir(parents=True)
    tex = paper_dir / "source.tex"
    tex.write_text(r"""
\documentclass{article}
\title{Test Paper}
\author{Test Author}
\begin{document}
\maketitle
\section{Introduction}
This is a test.
\section{Methods}
We did something.
\section{Results}
It worked.
\end{document}
""")
    cache.upsert({"key": key, "title": "Test Paper", "state": "tex", "tex_path": str(tex)})
    return key


def test_ara_dir(paper_with_tex, tmp_library):
    key = paper_with_tex
    expected = tmp_library / "library" / key / "ara"
    assert ara.ara_dir(key) == expected


def test_is_compiled_false(paper_with_tex):
    assert not ara.is_compiled(paper_with_tex)


def test_is_compiled_true(paper_with_tex, tmp_library):
    key = paper_with_tex
    ara_d = tmp_library / "library" / key / "ara"
    ara_d.mkdir(parents=True)
    (ara_d / "PAPER.md").write_text("# Test")
    assert ara.is_compiled(key)


def test_compile_ara_already_compiled(paper_with_tex, tmp_library):
    key = paper_with_tex
    ara_d = tmp_library / "library" / key / "ara"
    ara_d.mkdir(parents=True)
    (ara_d / "PAPER.md").write_text("# Test")
    result = ara.compile_ara(key)
    assert result["already_compiled"] is True
    assert result["state"] == "ara"


def test_compile_ara_no_tex():
    cache.upsert({"key": "nolatex", "title": "No LaTeX", "state": "metadata"})
    result = ara.compile_ara("nolatex")
    assert "error" in result
    assert "no LaTeX source" in result["error"]


def test_read_ara_layer_not_compiled(paper_with_tex):
    result = ara.read_ara_layer(paper_with_tex, "claims")
    assert "error" in result
    assert "no compiled ARA" in result["error"]


def test_read_ara_layer_paper(paper_with_tex, tmp_library):
    key = paper_with_tex
    ara_d = tmp_library / "library" / key / "ara"
    ara_d.mkdir(parents=True)
    (ara_d / "PAPER.md").write_text("---\ntitle: Test\n---\n# Test Paper\n")
    result = ara.read_ara_layer(key, "paper")
    assert result["layer"] == "paper"
    assert "Test Paper" in result["text"]


def test_read_ara_layer_all_files(paper_with_tex, tmp_library):
    key = paper_with_tex
    ara_d = tmp_library / "library" / key / "ara"
    (ara_d / "logic").mkdir(parents=True)
    (ara_d / "PAPER.md").write_text("# Test")
    (ara_d / "logic" / "claims.md").write_text("## C01")
    result = ara.read_ara_layer(key, "all_files")
    assert "PAPER.md" in result["files"]
    assert "logic/claims.md" in result["files"]


def test_read_ara_layer_missing_layer(paper_with_tex, tmp_library):
    key = paper_with_tex
    ara_d = tmp_library / "library" / key / "ara"
    ara_d.mkdir(parents=True)
    (ara_d / "PAPER.md").write_text("# Test")
    result = ara.read_ara_layer(key, "heuristics")
    assert "error" in result
    assert "available_files" in result


def test_skill_file_exists():
    assert ara.SKILL_PATH.exists()
    content = ara.SKILL_PATH.read_text()
    assert "Universal ARA Compiler" in content


def test_build_compiler_prompt(paper_with_tex, tmp_library):
    key = paper_with_tex
    paper = cache.get(key)
    prompt = ara._build_compiler_prompt(paper["tex_path"], str(ara.ara_dir(key)))
    assert "4-Stage Epistemic" in prompt or "Semantic Deconstruction" in prompt
    assert paper["tex_path"] in prompt
