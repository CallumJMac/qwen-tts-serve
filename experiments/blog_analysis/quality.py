# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = [
#   "faster-whisper==1.1.1",
#   "jiwer==3.1.0",
#   "numpy>=1.26,<2.3",
#   "soundfile==0.13.1",
#   "speechbrain==1.0.3",
#   "torch==2.5.1",
#   "torchaudio==2.5.1",
#   "huggingface-hub<0.27",
# ]
# ///
"""Objective quality checks on retained audio.

For each clip this records: ASR word error rate against the input text,
leading and trailing silence, and (for full versus streamed pairs) ECAPA
speaker-embedding cosine similarity. ASR is an intelligibility proxy, not a
perceptual quality score.

Run from the repository root:

    uv run experiments/blog_analysis/quality.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import jiwer
import numpy as np
import soundfile
import torch
from faster_whisper import WhisperModel
from speechbrain.inference.speaker import EncoderClassifier

REPO_ROOT = Path(__file__).resolve().parents[2]
QUALITY_DIR = REPO_ROOT / "experiments/results/20260715-a10g/quality"
TTFA_DIR = REPO_ROOT / "artifacts/20260722T091317Z-ttfa"
OUTPUT_PATH = REPO_ROOT / "experiments/blog_analysis/output/quality.json"
ASR_MODEL = "small.en"
SPEAKER_MODEL = "speechbrain/spkrec-ecapa-voxceleb"
SILENCE_DBFS = -45.0
FRAME_SECONDS = 0.02

NUMBER_WORDS = {
    "9:45": "nine forty five",
}


def normalise(text: str) -> str:
    lowered = text.lower()
    for written, spoken in NUMBER_WORDS.items():
        lowered = lowered.replace(written, spoken)
    lowered = lowered.replace("-", " ")
    lowered = re.sub(r"[^a-z0-9' ]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def silence_profile(samples: np.ndarray, sample_rate: int) -> dict[str, float]:
    frame_length = int(FRAME_SECONDS * sample_rate)
    frame_count = len(samples) // frame_length
    frames = samples[: frame_count * frame_length].reshape(frame_count, frame_length)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1)) + 1e-12
    voiced = np.flatnonzero(20 * np.log10(rms) > SILENCE_DBFS)
    duration = len(samples) / sample_rate
    if voiced.size == 0:
        return {"duration_s": duration, "leading_silence_s": duration, "trailing_silence_s": 0.0}
    return {
        "duration_s": duration,
        "leading_silence_s": voiced[0] * FRAME_SECONDS,
        "trailing_silence_s": duration - (voiced[-1] + 1) * FRAME_SECONDS,
    }


class Scorer:
    def __init__(self) -> None:
        self.asr = WhisperModel(ASR_MODEL, device="cpu", compute_type="int8")
        self.speaker = EncoderClassifier.from_hparams(
            source=SPEAKER_MODEL, savedir=str(REPO_ROOT / ".cache/spkrec-ecapa")
        )

    def score(self, path: Path, reference_text: str) -> dict:
        samples, sample_rate = soundfile.read(path, dtype="float32")
        segments, _info = self.asr.transcribe(str(path), beam_size=5, language="en")
        hypothesis = " ".join(segment.text for segment in segments).strip()
        return {
            "path": str(path.relative_to(REPO_ROOT)),
            "reference": reference_text,
            "transcript": hypothesis,
            "wer": jiwer.wer(normalise(reference_text), normalise(hypothesis)),
            **silence_profile(samples, sample_rate),
        }

    def embedding(self, path: Path) -> torch.Tensor:
        samples, sample_rate = soundfile.read(path, dtype="float32")
        waveform = torch.from_numpy(samples).unsqueeze(0)
        if sample_rate != 16000:
            import torchaudio

            waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
        return self.speaker.encode_batch(waveform).squeeze()

    def similarity(self, first: Path, second: Path) -> float:
        return float(
            torch.nn.functional.cosine_similarity(
                self.embedding(first), self.embedding(second), dim=0
            )
        )


def streaming_pairs(scorer: Scorer) -> list[dict]:
    corpus = json.loads((REPO_ROOT / "experiments/corpus.json").read_text())["quality"]
    pairs = []
    for record in map(json.loads, (QUALITY_DIR / "runs.jsonl").read_text().splitlines()):
        case = record["case"]
        full_path = QUALITY_DIR / "audio" / f"{case}-full.wav"
        streamed_path = QUALITY_DIR / "audio" / f"{case}-streamed.wav"
        pairs.append(
            {
                "case": case,
                "full": scorer.score(full_path, corpus[case]),
                "streamed": scorer.score(streamed_path, corpus[case]),
                "speaker_similarity": scorer.similarity(full_path, streamed_path),
                "waveform_metrics": record["metrics"],
            }
        )
    return pairs


def packet_study_clips(scorer: Scorer) -> list[dict]:
    """Score one retained clip per prompt for every packet-study condition."""
    # The packet study used the same 20 prompts as the capacity study.
    corpus = json.loads((REPO_ROOT / "experiments/capacity-corpus.json").read_text())["capacity"]
    clips = []
    for condition_dir in sorted((TTFA_DIR / "conditions").iterdir()):
        if not condition_dir.is_dir():
            continue
        seen_cases: set[str] = set()
        for record in map(json.loads, (condition_dir / "runs.jsonl").read_text().splitlines()):
            if record.get("status") != "ok" or record["case"] in seen_cases:
                continue
            retained = record.get("retained_audio")
            if not retained:
                continue
            seen_cases.add(record["case"])
            scored = scorer.score(condition_dir / retained["path"], corpus[record["case"]])
            clips.append({"condition": record["condition"], "case": record["case"], **scored})
    return clips


def main() -> None:
    scorer = Scorer()
    result = {
        "asr_model": ASR_MODEL,
        "speaker_model": SPEAKER_MODEL,
        "silence_threshold_dbfs": SILENCE_DBFS,
        "streaming_pairs": streaming_pairs(scorer),
        "packet_study_clips": packet_study_clips(scorer),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
