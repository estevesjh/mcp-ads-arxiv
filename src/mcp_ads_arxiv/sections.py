"""Heading normalization, fuzzy resolution, and robust section extraction.

upstream `arxiv_to_prompt.list_sections` returns the raw brace contents of `\\section{...}`,
which include LaTeX macros (`\\chandra`), embedded newlines, and trailing whitespace. upstream
`extract_section` is brittle about whitespace in those names, so we extract directly from the
parsed section tree (byte ranges) rather than going through the buggy by-name lookup.
"""

from __future__ import annotations

import re

from arxiv_to_prompt.core import SectionNode, parse_section_tree

# `\macro` or `\macro\` (the trailing backslash form like `\chandra\`).
_LATEX_MACRO = re.compile(r"\\[A-Za-z]+\\?")
_BRACES = re.compile(r"[{}]")
_NON_WORD = re.compile(r"[^\w\s\-]")
_WS = re.compile(r"\s+")

# Topic aliases: canonical label -> ordered list of substrings to look for in headings.
# Ordered: earlier matches win when several headings would match.
TOPIC_ALIASES: dict[str, list[str]] = {
    "abstract": ["abstract"],
    "introduction": ["introduction", "background"],
    "methodology": [
        "method", "model", "data analysis", "data reduction", "approach", "framework",
        "equation", "formalism",
    ],
    "results": ["result", "fits", "best.?fit", "measurement", "mass measurement"],
    "discussion": ["discussion", "comparison"],
    "conclusions": ["conclusion", "summary"],
    "acknowledgments": ["acknowledg"],
}


def normalize_heading(h: str) -> str:
    """Lowercase, drop LaTeX macros + braces + punctuation, collapse whitespace."""
    s = _LATEX_MACRO.sub(" ", h)
    s = _BRACES.sub(" ", s)
    s = _NON_WORD.sub(" ", s)
    s = _WS.sub(" ", s).strip().lower()
    return s


def display_label(h: str) -> str:
    """Friendly title-cased label for `list_sections` output. Stable across LaTeX quirks."""
    norm = normalize_heading(h)
    return norm.title() if norm else h.strip()


_STOPWORDS = {"the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with"}


def _content_tokens(s: str) -> set[str]:
    return {w for w in normalize_heading(s).split() if w and w not in _STOPWORDS}


def resolve_section(query: str, raw_headings: list[str]) -> str | None:
    """Map a user-supplied section name to the raw heading needed by extract_section.

    Order: exact normalized match -> substring match either way -> token-overlap match
    (best-scoring heading whose content words are mostly contained by the query and vice
    versa). Returns None if nothing matches.
    """
    if not query:
        return None
    q = normalize_heading(query)
    norm_to_raw = {normalize_heading(h): h for h in raw_headings}
    if q in norm_to_raw:
        return norm_to_raw[q]
    for n, raw in norm_to_raw.items():
        if n and (q in n or n in q):
            return raw
    # Token-overlap fallback. Pick the heading with the highest Jaccard score that also
    # has at least one content-word match.
    qt = _content_tokens(query)
    if not qt:
        return None
    best: tuple[float, str] | None = None
    for raw in raw_headings:
        ht = _content_tokens(raw)
        if not ht:
            continue
        overlap = qt & ht
        if not overlap:
            continue
        jaccard = len(overlap) / len(qt | ht)
        if best is None or jaccard > best[0]:
            best = (jaccard, raw)
    if best and best[0] >= 0.4:  # require meaningful overlap
        return best[1]
    return None


def _flatten_tree(nodes: list[SectionNode]) -> list[SectionNode]:
    out: list[SectionNode] = []
    for n in nodes:
        out.append(n)
        out.extend(_flatten_tree(n.children))
    return out


def extract_by_raw_name(text: str, raw_name: str) -> str:
    """Extract a section by its raw heading using upstream's parsed tree (byte-range based).

    Works around a bug where upstream's by-name lookup compares against `parts[0].strip()`
    while the parsed `node.name` keeps trailing whitespace, so headings like
    'Application to \\\\chandra\\\\ Observations of Clusters ' fail to match themselves.
    """
    if not raw_name:
        return ""
    flat = _flatten_tree(parse_section_tree(text))
    for n in flat:
        if n.name == raw_name:
            return text[n.start_pos:n.end_pos].rstrip()
    target = normalize_heading(raw_name)
    for n in flat:
        if normalize_heading(n.name) == target:
            return text[n.start_pos:n.end_pos].rstrip()
    return ""


def resolve_topic(topic: str, raw_headings: list[str]) -> list[str]:
    """Resolve a natural-language topic ('methodology', 'results', ...) to raw headings.

    Returns ALL headings whose normalized text matches any alias for the topic, in document
    order. Falls back to a substring resolve against the topic string itself when the topic
    isn't in TOPIC_ALIASES.
    """
    aliases = TOPIC_ALIASES.get(topic.strip().lower())
    norms = [(normalize_heading(h), h) for h in raw_headings]
    if aliases:
        out: list[str] = []
        seen: set[str] = set()
        for pattern in aliases:
            rx = re.compile(pattern)
            for norm, raw in norms:
                if rx.search(norm) and raw not in seen:
                    out.append(raw)
                    seen.add(raw)
        return out
    # Unknown topic: treat as a free-text substring query.
    one = resolve_section(topic, raw_headings)
    return [one] if one else []
