"""Loaders for the retained experiment records used by the blog analysis."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "experiments/results"
CAPACITY_RUN_ID = "20260716T121717Z"
ENDPOINT_RUN_DIR = RESULTS_DIR / "20260715-a10g"
PACKET_STUDY_DIR = REPO_ROOT / "artifacts/20260722T091317Z-ttfa"

CAPACITY_PATTERN = re.compile(
    rf"{CAPACITY_RUN_ID}-capacity-(?P<backend>current|omni)-(?P<profile>closed|open)-(?P<load>[\d.]+)$"
)
PACKET_PATTERN = re.compile(
    r"(?P<backend>current|omni)-(?P<route>alb|localhost)-(?P<profile>isolated|sustained)"
    r"-frames-(?P<frames>\d+)$"
)


@dataclass(frozen=True)
class CapacityCondition:
    backend: str
    profile: str
    load: float


@dataclass(frozen=True)
class PacketCondition:
    backend: str
    route: str
    profile: str
    frames: int


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def successful(records: list[dict]) -> list[dict]:
    return [record for record in records if record.get("status") == "ok"]


def load_capacity() -> dict[CapacityCondition, list[dict]]:
    conditions: dict[CapacityCondition, list[dict]] = {}
    for directory in sorted(RESULTS_DIR.iterdir()):
        match = CAPACITY_PATTERN.match(directory.name)
        if not match:
            continue
        (runs_path,) = directory.glob("*/runs.jsonl")
        key = CapacityCondition(match["backend"], match["profile"], float(match["load"]))
        conditions[key] = read_jsonl(runs_path)
    return conditions


def load_packet_study() -> dict[PacketCondition, list[dict]]:
    conditions: dict[PacketCondition, list[dict]] = {}
    for directory in sorted((PACKET_STUDY_DIR / "conditions").iterdir()):
        match = PACKET_PATTERN.match(directory.name)
        if not match or not directory.is_dir():
            continue
        key = PacketCondition(
            match["backend"], match["route"], match["profile"], int(match["frames"])
        )
        conditions[key] = read_jsonl(directory / "runs.jsonl")
    return conditions


def load_packet_latency_budget() -> list[dict]:
    budget = json.loads((PACKET_STUDY_DIR / "analysis/latency-budget.json").read_text())
    return budget["conditions"]


def load_endpoint_runs() -> list[dict]:
    return read_jsonl(ENDPOINT_RUN_DIR / "endpoint/runs.jsonl")


def load_throughput_runs() -> list[dict]:
    return read_jsonl(ENDPOINT_RUN_DIR / "throughput/runs.jsonl")


def load_capacity_corpus() -> dict[str, str]:
    return json.loads((REPO_ROOT / "experiments/capacity-corpus.json").read_text())["capacity"]
