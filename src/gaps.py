"""Reproducible contiguous gaps with an identical visible support for every method."""

import numpy as np


def make_masks(frames, times, gap_sizes, support_per_side, repetitions, seed):
    frames = np.asarray(frames, dtype=int)
    times = np.asarray(times, dtype=float)
    if (frames.ndim != 1 or times.shape != frames.shape
            or np.any(np.diff(frames) <= 0) or np.any(np.diff(times) <= 0)
            or not np.isfinite(times).all()):
        raise ValueError("Frames and times must be aligned and strictly increasing")
    if support_per_side < 1 or repetitions < 1 or any(g < 1 for g in gap_sizes):
        raise ValueError("Support, repetition count and gap sizes must be positive")
    rng = np.random.default_rng(seed)
    masks = []
    k = support_per_side
    for gap in gap_sizes:
        candidates = []
        for start in range(k, len(frames) - gap - k + 1):
            # Entire local reference window must be observed at consecutive frames.
            window = frames[start - k:start + gap + k]
            if np.all(np.diff(window) == 1):
                candidates.append(start)
        if not candidates:
            continue
        starts = sorted(rng.choice(candidates, size=min(repetitions, len(candidates)), replace=False))
        for start in starts:
            hidden = np.arange(start, start + gap)
            visible = np.r_[np.arange(start - k, start), np.arange(start + gap, start + gap + k)]
            masks.append({
                "gap_size": int(gap), "seed": int(seed), "kind": "contiguous",
                "hidden_indices": hidden.tolist(), "visible_indices": visible.tolist(),
                "hidden_frames": frames[hidden].tolist(), "visible_frames": frames[visible].tolist(),
                "hidden_timestamps_s": times[hidden].tolist(),
                "bracket_duration_s": float(times[start + gap] - times[start - 1]),
                "hidden_span_s": float(times[start + gap - 1] - times[start]),
            })
    return masks


def make_continuous_masks(frames, times, gap_sizes, support_per_side, seed):
    """Tile every continuous observed run with gaps and globally visible anchors.

    The k observations between two gaps can support both gaps, but no hidden
    observation in this schedule may ever be used by another gap's interpolator.
    No cap on repetitions: traverse every eligible run from beginning to end.
    """
    frames = np.asarray(frames, dtype=int)
    times = np.asarray(times, dtype=float)
    k = support_per_side
    if (frames.ndim != 1 or times.shape != frames.shape or k < 1
            or not gap_sizes or any(g < 1 or int(g) != g for g in gap_sizes)
            or not np.isfinite(times).all() or np.any(np.diff(times) <= 0)
            or np.any(np.diff(frames) <= 0)):
        raise ValueError("Invalid frames, timestamps or continuous-mask settings")
    rng = np.random.default_rng(seed)
    cycle = rng.permutation(gap_sizes).tolist()
    edges = np.r_[0, np.flatnonzero(np.diff(frames) != 1) + 1, len(frames)]
    masks = []
    cycle_index = 0
    for begin, end in zip(edges[:-1], edges[1:]):
        start = int(begin) + k
        while start + min(gap_sizes) + k <= end:
            room = int(end) - start - k
            gap = cycle[cycle_index % len(cycle)]
            if gap > room:
                gap = max(g for g in gap_sizes if g <= room)
            hidden = np.arange(start, start + gap)
            visible = np.r_[np.arange(start - k, start), np.arange(start + gap, start + gap + k)]
            masks.append({
                "gap_size": int(gap), "seed": int(seed), "kind": "continuous_schedule",
                "hidden_indices": hidden.tolist(), "visible_indices": visible.tolist(),
                "hidden_frames": frames[hidden].tolist(), "visible_frames": frames[visible].tolist(),
                "hidden_timestamps_s": times[hidden].tolist(),
                "bracket_duration_s": float(times[start + gap] - times[start - 1]),
                "hidden_span_s": float(times[start + gap - 1] - times[start]),
            })
            start += int(gap) + k
            cycle_index += 1
    return masks
