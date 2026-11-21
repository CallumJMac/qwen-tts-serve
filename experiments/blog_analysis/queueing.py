"""Single-server FIFO queue model for the serialised backend."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def fifo_waits(arrivals: Sequence[float], services: Sequence[float]) -> list[float]:
    """Return each request's wait before service on one first-in, first-out server."""
    if len(arrivals) != len(services):
        raise ValueError("arrivals and services must have equal length")
    order = np.argsort(arrivals, kind="stable")
    waits = [0.0] * len(arrivals)
    server_free_at = float("-inf")
    for index in order:
        start = max(arrivals[index], server_free_at)
        waits[index] = start - arrivals[index]
        server_free_at = start + services[index]
    return waits


def pollaczek_khinchine_mean_wait(arrival_rate: float, services: Sequence[float]) -> float:
    """Steady-state mean queue wait for an M/G/1 queue; infinite when utilisation >= 1."""
    service_array = np.asarray(services, dtype=float)
    utilisation = arrival_rate * service_array.mean()
    if utilisation >= 1:
        return float("inf")
    return float(arrival_rate * np.mean(service_array**2) / (2 * (1 - utilisation)))
