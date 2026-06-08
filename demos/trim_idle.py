#!/usr/bin/env python3
# Source: https://github.com/cbyrohl/mcp-server-ads/blob/main/demos/trim_idle.py (MIT)
"""Trim idle frames from a GIF.

Detects sequences of near-identical frames (e.g. blinking cursor, no real
content change) and collapses them to a short pause, keeping all "action"
frames at their original speed.

Usage:
    uvx --with Pillow --with numpy python demos/trim_idle.py demos/demo.gif demos/demo_trimmed.gif

Options (positional):
    input_gif       Input GIF path
    output_gif      Output GIF path
    --threshold     Fraction of changed pixels below which frames are "idle" (default: 0.02)
    --max-idle-ms   Maximum total duration for an idle stretch in ms (default: 300)
"""

import argparse
import sys

import numpy as np
from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True


def load_frames(path):
    """Load all frames from a GIF with their durations."""
    img = Image.open(path)
    frames = []
    try:
        while True:
            frame = img.convert("RGB")
            duration = img.info.get("duration", 100)
            frames.append((frame.copy(), duration))
            img.seek(img.tell() + 1)
    except EOFError:
        pass
    return frames


def frame_diff(a, b):
    """Fraction of pixels that changed significantly (>30 intensity units).

    More robust than mean-pixel-diff for terminal recordings: a blinking cursor
    or spinner changes <1% of pixels but can spike the mean if the rest is dark.
    Returns the fraction [0..1] of pixels that differ.
    """
    arr_a = np.asarray(a, dtype=np.int16)
    arr_b = np.asarray(b, dtype=np.int16)
    per_pixel = np.max(np.abs(arr_a - arr_b), axis=-1)  # max channel diff per pixel
    changed = np.count_nonzero(per_pixel > 30)
    return changed / per_pixel.size


def trim_idle(frames, threshold=0.001, max_idle_ms=800, content_hold_ms=2000):
    """Collapse runs of near-identical frames; hold content frames longer.

    - Idle stretches (diff < threshold) collapse to max_idle_ms.
    - Content frames (diff >= threshold) keep at least content_hold_ms
      so the reader can absorb new text/tables.
    """
    result = []
    idle_run = []

    for i, (frame, duration) in enumerate(frames):
        if i == 0:
            result.append((frame, duration))
            continue

        diff = frame_diff(frames[i - 1][0], frame)

        if diff < threshold:
            idle_run.append((frame, duration))
        else:
            # Flush idle run
            if idle_run:
                total_idle = sum(d for _, d in idle_run)
                capped = min(total_idle, max_idle_ms)
                result.append((idle_run[-1][0], capped))
                idle_run = []
            # Content frame: ensure minimum hold time for readability
            hold = max(duration, content_hold_ms) if diff > threshold * 5 else duration
            result.append((frame, hold))

    # Flush trailing idle
    if idle_run:
        total_idle = sum(d for _, d in idle_run)
        capped = min(total_idle, max_idle_ms)
        result.append((idle_run[-1][0], capped))

    return result


def save_gif(frames, path):
    """Save frames as an animated GIF."""
    if not frames:
        print("No frames to save.", file=sys.stderr)
        sys.exit(1)

    images = [f for f, _ in frames]
    durations = [d for _, d in frames]

    images[0].save(
        path,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )


def main():
    parser = argparse.ArgumentParser(description="Trim idle frames from a GIF")
    parser.add_argument("input_gif", help="Input GIF path")
    parser.add_argument("output_gif", help="Output GIF path")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.02,
        help="Fraction of changed pixels below which frames are idle (default: 0.02)",
    )
    parser.add_argument(
        "--max-idle-ms",
        type=int,
        default=800,
        help="Max total duration for an idle stretch in ms (default: 800)",
    )
    parser.add_argument(
        "--content-hold-ms",
        type=int,
        default=2000,
        help="Min hold time for frames with significant new content in ms (default: 2000)",
    )
    args = parser.parse_args()

    print(f"Loading {args.input_gif}...")
    frames = load_frames(args.input_gif)
    print(f"  {len(frames)} frames loaded")

    original_duration = sum(d for _, d in frames)
    print(f"  Original duration: {original_duration / 1000:.1f}s")

    print(f"Trimming (threshold={args.threshold}, max_idle={args.max_idle_ms}ms, "
          f"content_hold={args.content_hold_ms}ms)...")
    trimmed = trim_idle(frames, threshold=args.threshold, max_idle_ms=args.max_idle_ms,
                        content_hold_ms=args.content_hold_ms)
    trimmed_duration = sum(d for _, d in trimmed)
    print(f"  {len(frames)} -> {len(trimmed)} frames")
    print(f"  Duration: {original_duration / 1000:.1f}s -> {trimmed_duration / 1000:.1f}s")

    print(f"Saving {args.output_gif}...")
    save_gif(trimmed, args.output_gif)
    print("Done.")


if __name__ == "__main__":
    main()
