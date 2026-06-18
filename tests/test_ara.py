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
\title{Test Paper on Dark Matter Halos}
\author{Test Author}
\begin{document}
\maketitle
\begin{abstract}
We present a model of dark matter halos.
\end{abstract}
\section{Introduction}
This is a test paper about halo models \cite{NFW97}.
\section{Methods}
We solve the equation:
\begin{equation}
\rho(r) = \frac{\rho_0}{(r/r_s)(1+r/r_s)^2}
\end{equation}
\section{Results}
\begin{table}
\caption{Halo parameters}
\label{tab:params}
\begin{tabular}{lcc}
\hline
Name & Mass & Concentration \\
\hline
Halo A & $10^{14}$ & 5.2 \\
\end{tabular}
\end{table}
\begin{figure}
\includegraphics[width=8cm]{fig1.eps}
\caption{Density profile}
\label{fig:density}
\end{figure}
\section{Discussion and Conclusions}
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
    (ara_d / "logic").mkdir(parents=True)
    (ara_d / "PAPER.md").write_text("# Test")
    (ara_d / "logic" / "claims.md").write_text("## C01")
    assert ara.is_compiled(key)


def test_read_ara_layer_not_compiled(paper_with_tex):
    result = ara.read_ara_layer(paper_with_tex, "claims")
    assert "error" in result
    assert "no compiled ARA" in result["error"]


def test_read_ara_layer_paper(paper_with_tex, tmp_library):
    key = paper_with_tex
    ara_d = tmp_library / "library" / key / "ara"
    (ara_d / "logic").mkdir(parents=True)
    (ara_d / "PAPER.md").write_text("---\ntitle: Test\n---\n# Test Paper\n")
    (ara_d / "logic" / "claims.md").write_text("## C01")
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
    (ara_d / "logic").mkdir(parents=True)
    (ara_d / "PAPER.md").write_text("# Test")
    (ara_d / "logic" / "claims.md").write_text("## C01")
    result = ara.read_ara_layer(key, "heuristics")
    assert "error" in result
    assert "available_files" in result


def test_skill_file_exists():
    assert ara.SKILL_PATH.exists()
    content = ara.SKILL_PATH.read_text()
    assert "Universal ARA Compiler" in content


def test_extract_atoms(paper_with_tex, tmp_library):
    key = paper_with_tex
    paper = cache.get(key)
    atoms = ara.extract_atoms(paper["tex_path"])
    assert atoms["title"] == "Test Paper on Dark Matter Halos"
    assert "dark matter halos" in atoms["abstract"].lower()
    assert len(atoms["sections"]) >= 3
    assert len(atoms["equations"]) == 1
    assert len(atoms["tables"]) == 1
    assert atoms["tables"][0]["caption"] == "Halo parameters"
    assert len(atoms["figures"]) == 1
    assert atoms["figures"][0]["files"] == ["fig1.eps"]
    assert "NFW97" in atoms["cite_keys"]


def test_validate_ara_missing_files(tmp_path):
    issues = ara._validate_ara(tmp_path)
    assert len(issues) >= 10  # All mandatory files missing


def test_validate_ara_complete(tmp_path):
    (tmp_path / "logic" / "solution").mkdir(parents=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "trace").mkdir()
    (tmp_path / "evidence").mkdir()
    for f in ["PAPER.md", "logic/problem.md", "logic/claims.md", "logic/concepts.md",
              "logic/experiments.md", "logic/related_work.md",
              "logic/solution/constraints.md", "src/environment.md",
              "trace/exploration_tree.yaml", "evidence/README.md"]:
        (tmp_path / f).write_text("content")
    issues = ara._validate_ara(tmp_path)
    assert len(issues) == 0
