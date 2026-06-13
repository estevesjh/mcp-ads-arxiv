"""Serve-time LaTeX noise stripper.

Cached `source.tex` stays raw on disk so section parsing keeps its byte-range fidelity
(arxiv_to_prompt's parse_section_tree needs the original headings). This module runs only on
the snippet about to be handed to the model, removing structural weight that costs tokens but
carries no meaning Claude can use:

  - comments (`% ...`)
  - pure layout/packaging preamble (`\\documentclass`, `\\usepackage`, `\\setlength`, ...)
  - float bodies (`figure`/`table` and starred variants): collapsed to ONLY the `\\caption{...}`
    text — the `\\psfig`/`\\includegraphics`/`tabular` plumbing is dropped. Captions describe the
    science and are often referenced in the prose.
  - `\\label{...}` anchors

Deliberately PRESERVED (do not strip):
  - macro definitions (`\\newcommand`, `\\def`, `\\DeclareMathOperator`, ...) — the body uses
    these macros inside equations; dropping the defs would leave undefined symbols.
  - equations, citations, `\\ref`/`\\autoref` calls, prose.

The IRON RULE that the model reads real LaTeX (equations intact) still holds.
"""

from __future__ import annotations

import re

# `% ...` to end of line, but not an escaped `\%`.
_COMMENT = re.compile(r"(?<!\\)%.*$", re.M)

# Whole-line PURE LAYOUT/PACKAGING preamble. Macro-defining commands (newcommand, def,
# DeclareMathOperator, ...) are intentionally absent — they define symbols the body needs.
# `include` excludes `includegraphics`.
_PREAMBLE = re.compile(
    r"^[ \t]*\\(?:documentclass|usepackage|RequirePackage|let|input|include(?!graphics)|"
    r"bibliographystyle|pdfoutput|defcitealias|captionsetup|hypersetup|pagestyle|"
    r"setlength|setcounter|newtheorem|theoremstyle|usetikzlibrary|graphicspath).*$",
    re.M,
)

_FLOAT_ENVS = "figure\\*?|table\\*?|wrapfigure|sidewaysfigure|sidewaystable"
# Float environments -> replaced by their caption only. Non-greedy; \1 pairs begin/end.
_FLOAT = re.compile(rf"\\begin\{{({_FLOAT_ENVS})\}}.*?\\end\{{\1\}}", re.S)
_CAPTION = re.compile(r"\\caption(?:\[[^\]]*\])?\{")

_LABEL = re.compile(r"\\label\{[^}]*\}")
_BLANKS = re.compile(r"\n{3,}")


def _balanced(text: str, start: int) -> tuple[str, int]:
    """Return the brace-balanced content beginning at `start` (just past an opening `{`),
    and the index just past its matching `}`."""
    depth = 1
    i = start
    n = len(text)
    while i < n and depth:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return text[start : i - 1], i


def _caption_text(block: str) -> str:
    """Extract the `\\caption{...}` content from a float block, or '' if it has none."""
    m = _CAPTION.search(block)
    if not m:
        return ""
    body, _ = _balanced(block, m.end())
    return body.strip()


def _replace_float(m: re.Match[str]) -> str:
    return _caption_text(m.group(0))


def clean_latex(text: str) -> str:
    """Strip LaTeX layout noise from a snippet bound for the model. Idempotent."""
    if not text:
        return text
    text = _COMMENT.sub("", text)
    text = _FLOAT.sub(_replace_float, text)
    text = _PREAMBLE.sub("", text)
    text = _LABEL.sub("", text)
    text = _BLANKS.sub("\n\n", text)
    return text.strip()
