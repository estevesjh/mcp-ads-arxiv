"""Terminal progress bar that writes to STDERR.

An MCP stdio server uses STDOUT for JSON-RPC, so anything human-facing (logs, progress)
must go to STDERR or it corrupts the protocol.
"""

from __future__ import annotations

import sys
from typing import IO


def download_bar(downloaded: int, total: int, *, label: str = "", width: int = 30,
                 stream: IO[str] = sys.stderr) -> None:
    """Render a single-line progress bar. Call repeatedly; pass total<=0 if unknown."""
    if total > 0:
        frac = min(1.0, downloaded / total)
        filled = int(width * frac)
        bar = "#" * filled + "-" * (width - filled)
        msg = f"\r{label} [{bar}] {frac * 100:5.1f}% ({downloaded}/{total} B)"
    else:
        spin = "|/-\\"[(downloaded // 1024) % 4]
        msg = f"\r{label} [{spin}] {downloaded} B"
    stream.write(msg)
    stream.flush()
    if total > 0 and downloaded >= total:
        stream.write("\n")
        stream.flush()


def done(label: str = "", stream: IO[str] = sys.stderr) -> None:
    stream.write(f"\r{label} done.\n")
    stream.flush()
