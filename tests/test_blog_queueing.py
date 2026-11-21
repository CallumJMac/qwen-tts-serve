import math

from experiments.blog_analysis.queueing import fifo_waits, pollaczek_khinchine_mean_wait


def test_fifo_waits_queue_behind_busy_server() -> None:
    assert fifo_waits([0.0, 1.0, 5.0], [3.0, 3.0, 1.0]) == [0.0, 2.0, 1.0]


def test_fifo_waits_respects_arrival_order_not_input_order() -> None:
    assert fifo_waits([2.0, 0.0], [1.0, 3.0]) == [1.0, 0.0]


def test_pollaczek_khinchine_matches_md1_formula() -> None:
    # M/D/1 with service 1s and arrival rate 0.5/s: Wq = rho / (2 mu (1 - rho)) = 0.5s.
    assert math.isclose(pollaczek_khinchine_mean_wait(0.5, [1.0, 1.0]), 0.5)


def test_pollaczek_khinchine_is_unbounded_at_full_utilisation() -> None:
    assert pollaczek_khinchine_mean_wait(1.0, [1.0]) == math.inf
