from mcp_ads_arxiv.latexclean import clean_latex


def test_strips_comments_but_keeps_escaped_percent():
    src = "Real text 50\\% done % this is a comment\nnext line"
    out = clean_latex(src)
    assert "this is a comment" not in out
    assert "50\\%" in out
    assert "next line" in out


def test_drops_figure_plumbing_but_keeps_caption():
    src = (
        "Intro prose.\n"
        "\\begin{figure*}[t]\n\\centerline{\\psfig{file=f1.eps}}\n"
        "\\caption{A long caption describing an image.}\n\\label{fig:x}\n\\end{figure*}\n"
        "More prose."
    )
    out = clean_latex(src)
    assert "A long caption describing an image." in out  # caption kept
    assert "psfig" not in out  # plumbing dropped
    assert "Intro prose." in out
    assert "More prose." in out


def test_keeps_table_caption_drops_tabular():
    src = (
        "Before.\n\\begin{table}\n\\caption{Fit parameters.}\n"
        "\\begin{tabular}{cc}1&2\\\\\\end{tabular}\n\\end{table}\nAfter."
    )
    out = clean_latex(src)
    assert "Fit parameters." in out
    assert "tabular" not in out
    assert "Before." in out and "After." in out


def test_strips_layout_preamble_but_keeps_macro_defs():
    src = (
        "\\documentclass{mnras}\n\\usepackage{amsmath}\n\\setlength{\\parindent}{0pt}\n"
        "\\newcommand{\\Msun}{M_\\odot}\n\\DeclareMathOperator{\\sinc}{sinc}\n"
        "\\section{Introduction}\nBody uses \\Msun."
    )
    out = clean_latex(src)
    assert "documentclass" not in out
    assert "usepackage" not in out
    assert "setlength" not in out
    assert "\\newcommand{\\Msun}{M_\\odot}" in out  # symbol def preserved
    assert "\\DeclareMathOperator{\\sinc}{sinc}" in out
    assert "\\section{Introduction}" in out
    assert "Body uses \\Msun." in out


def test_preserves_equations_and_citations():
    src = (
        "\\section{Method}\n"
        "We use \\citep{Foo2020} and derive\n"
        "\\begin{equation}\n\\rho(r) = \\rho_s e^{-b r}\n\\label{eq:rho}\n\\end{equation}\n"
        "as shown in \\autoref{eq:rho}."
    )
    out = clean_latex(src)
    assert "\\begin{equation}" in out
    assert "\\rho(r) = \\rho_s e^{-b r}" in out
    assert "\\citep{Foo2020}" in out
    assert "\\autoref{eq:rho}" in out
    assert "\\label{eq:rho}" not in out  # label anchor stripped


def test_idempotent():
    src = "\\usepackage{x}\n\\section{A}\nText % c\n\\begin{figure}\\caption{c}\\end{figure}\nMore."
    once = clean_latex(src)
    assert clean_latex(once) == once


def test_empty_input():
    assert clean_latex("") == ""
