# Blog analysis

Regenerates every statistic and figure in the two Qwen3-TTS blog posts from the retained
per-request records. No GPU is needed.

| Module        | Purpose                                                                    |
| ------------- | -------------------------------------------------------------------------- |
| `data.py`     | Loads the capacity study, packet-size study and 15 July endpoint runs.     |
| `stats.py`    | Linear-interpolated percentiles with percentile-bootstrap 95% intervals.   |
| `playback.py` | Replays chunk arrivals through a player with an optional startup buffer.   |
| `queueing.py` | Single-server FIFO replay and the M/G/1 Pollaczek-Khinchine mean wait.     |
| `analysis.py` | Writes `output/summary.json` and one CSV per figure.                       |
| `quality.py`  | Whisper ASR, leading/trailing silence and ECAPA speaker similarity.        |
| `figures.py`  | Renders themed SVGs (light and dark) into `output/figures/`.               |

Run from the repository root:

```bash
uv run experiments/blog_analysis/quality.py           # CPU, roughly 30 minutes
.venv/bin/python -m experiments.blog_analysis.analysis
uv run --no-project --with numpy --with 'matplotlib>=3.10,<3.11' \
  python -m experiments.blog_analysis.figures
.venv/bin/python -m pytest tests/test_blog_playback.py tests/test_blog_queueing.py
```

`quality.py` pins its own dependencies inline. `analysis.py` folds its output into
`summary.json` when `output/quality.json` exists.

## What is published

Every per-request record the analysis reads is included, so `analysis.py`,
`figures.py` and the tests run from a fresh clone. Re-running `quality.py` needs the
packet study's retained audio (146 MB), which is not published; its output,
`output/quality.json`, is. The full-versus-streamed pairs and the one clip shown in
the first-speech figure are included as WAV files. Host-level provenance (AWS
account, image registry and load-balancer details) is omitted.

## Definitions and caveats

- **Longest playback gap:** for each request, the longest interval in which the simulated
  player has no audio; SLOs apply to its 95th percentile across requests. With no buffer,
  `playback.py` reproduces the recorded `max_underrun_seconds` for all 1,200 capacity
  requests to within 1e-12 s.
- **Open-loop latency** is measured from the scheduled arrival: recorded TTFA plus
  `queue_wait_seconds`. The client capped in-flight requests at 32, so at 1 and 2 RPS
  the serialised server's requests waited up to 69 s before being sent.
- **Bootstrap intervals** resample requests. Outputs are deterministic per prompt, so the
  intervals reflect run-to-run timing noise on one host, not prompt or host variation.
- **Leading silence** is the time until a 20 ms frame first exceeds -45 dBFS.
- **Hosted API prices** in `analysis.py` are list prices accessed 2026-11-21.
