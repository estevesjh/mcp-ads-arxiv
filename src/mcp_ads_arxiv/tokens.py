"""Token measurement for payloads served to the model.

An MCP server cannot see Claude's actual billed token usage — that lives in the client. What we
CAN measure is the size, in tokens, of every payload we hand back, which is exactly the quantity
this token-optimizing library exists to minimize. We reuse arxiv-to-prompt's count_tokens (tiktoken
under the hood) and fall back to a ~4-chars-per-token heuristic if it is unavailable.
"""

from __future__ import annotations


def count(text: str) -> int:
    """Best-effort token count for a string."""
    if not text:
        return 0
    try:
        from arxiv_to_prompt import count_tokens

        return int(count_tokens(text))
    except Exception:
        return max(1, len(text) // 4)


def measure(text: str, full_text: str | None = None) -> dict[str, int]:
    """Token cost of `text`, and tokens saved versus `full_text` when a subset was served.

    Records the result into the cumulative counter and returns the per-response numbers.
    """
    from . import cache

    served = count(text)
    saved = 0
    if full_text is not None:
        saved = max(0, count(full_text) - served)
    cache.record_tokens(served, saved)
    return {"tokens_served": served, "tokens_saved": saved}
