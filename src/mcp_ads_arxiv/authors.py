"""Author-list shield: compress long author lists before they reach the model.

Physics collaborations list thousands of authors; dumping the full list into context
every time a paper's metadata is served is pure token waste. This module collapses
long lists to a few names plus a count. The FULL list is never altered here — it stays
in the SQLite registry and in literature_review.bib, where citations need it.
"""

from __future__ import annotations

import os

DEFAULT_MAX = 10
_LEAD = 3  # names shown before "et al." when a list is over the threshold


def display_max() -> int:
    """How many authors to show in full before collapsing. AUTHOR_DISPLAY_MAX env, default 10."""
    raw = os.environ.get("AUTHOR_DISPLAY_MAX")
    if raw:
        try:
            n = int(raw)
            if n > 0:
                return n
        except ValueError:
            pass
    return DEFAULT_MAX


def compress(authors: list[str]) -> str | list[str]:
    """Return the list unchanged if short, else 'A; B; C et al. (N authors)'.

    N is the true author count, comma-grouped (e.g. 2,340). The leading names keep
    their original "Last, First" form.
    """
    if not authors:
        return []
    n = len(authors)
    if n <= display_max():
        return authors
    lead = min(_LEAD, n)
    shown = "; ".join(str(a) for a in authors[:lead])
    return f"{shown} et al. ({n:,} authors)"
