"""Percentiles with bootstrap confidence intervals."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass

import numpy as np

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20260714


@dataclass(frozen=True)
class Estimate:
    value: float
    low: float
    high: float
    count: int

    def as_dict(self) -> dict:
        return asdict(self)


def percentile_with_ci(
    values: Sequence[float], percentile: float, confidence: float = 0.95
) -> Estimate:
    """Linear-interpolated percentile with a percentile-bootstrap interval.

    Requests are resampled with replacement. With deterministic per-prompt
    outputs, the interval reflects repeat-to-repeat timing noise over this
    corpus, not uncertainty about other prompts or hosts.
    """
    samples = np.asarray(values, dtype=float)
    if samples.size == 0:
        raise ValueError("cannot estimate a percentile of no values")
    generator = np.random.default_rng(BOOTSTRAP_SEED)
    indices = generator.integers(0, samples.size, size=(BOOTSTRAP_RESAMPLES, samples.size))
    resampled = np.percentile(samples[indices], percentile, axis=1)
    tail = (1 - confidence) / 2 * 100
    low, high = np.percentile(resampled, [tail, 100 - tail])
    return Estimate(
        value=float(np.percentile(samples, percentile)),
        low=float(low),
        high=float(high),
        count=int(samples.size),
    )
