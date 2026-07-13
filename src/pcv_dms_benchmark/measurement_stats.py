from __future__ import annotations

from statistics import fmean, median
from typing import Iterable


def summarize_samples(samples_ms: Iterable[float]) -> dict[str, float]:
    samples = [float(value) for value in samples_ms]
    if not samples:
        raise ValueError("at least one measurement sample is required")
    return {
        "p50_ms": median(samples),
        "mean_ms": fmean(samples),
    }
