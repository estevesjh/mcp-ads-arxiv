"""Pre-Flight Survey: cluster a set of paper metadata into focus/exclude options.

Pure and fast (no network). Aggregates ADS UAT keyword tags plus salient title terms into
frequency clusters, then proposes the 4 most common as focus tracks and the next 4 as
exclusion candidates. Claude presents these and waits for the user's choice.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "in", "on", "to", "with", "from", "by",
    "is", "are", "be", "as", "at", "via", "using", "use", "new", "study", "analysis",
    "observations", "observation", "data", "results", "towards", "toward", "into",
    "we", "this", "that", "their", "its", "our", "between", "based", "first", "two",
}

_WORD = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")


def _terms(papers: list[dict[str, Any]]) -> Counter:
    counter: Counter = Counter()
    for p in papers:
        for kw in p.get("keywords", []) or []:
            kw_norm = kw.strip().lower()
            if kw_norm and kw_norm not in _STOPWORDS:
                counter[kw_norm] += 3  # UAT tags weigh more than title words
        title = (p.get("title") or "").lower()
        for w in _WORD.findall(title):
            if w not in _STOPWORDS:
                counter[w] += 1
    return counter


def generate(papers: list[dict[str, Any]], n: int = 4) -> dict[str, Any]:
    """Return {focus: [...], exclude: [...], n_papers: int} option labels."""
    counter = _terms(papers)
    ranked = [term for term, _ in counter.most_common()]
    focus = ranked[:n]
    exclude = ranked[n : 2 * n]
    return {
        "n_papers": len(papers),
        "focus": focus,
        "exclude": exclude,
        "prompt": (
            "Pre-Flight Survey — choose before any full text is read:\n"
            f"  FOCUS on: {', '.join(focus) or '(none found)'}\n"
            f"  Candidates to EXCLUDE: {', '.join(exclude) or '(none)'}\n"
            "Reply with which topics to focus on and which to skip "
            "(e.g. 'focus dark-matter, skip instrumentation')."
        ),
    }
