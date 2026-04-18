from __future__ import annotations

import os
from collections.abc import Generator
from typing import Protocol

import numpy as np

SAMPLE_RATE = 24000
# Qwen3-TTS-12Hz codec frame rate: 12.5 tokens/sec (24000 Hz / 1920 samples per frame)
_TOKEN_RATE = 12.5


class TTSEngine(Protocol):
    def generate(self, text: str, language: str = "English") -> tuple[np.ndarray, int]: ...
    def generate_stream(
        self,
        text: str,
        language: str = "English",
        chunk_size: int = 12,
    ) -> Generator[tuple[np.ndarray, int]]: ...


class MockEngine:
    """Deterministic engine for testing. Produces a 0.5s sine wave."""

    def generate(self, text: str, language: str = "English") -> tuple[np.ndarray, int]:
        duration = 0.5
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), dtype=np.float32)
        return np.sin(2 * np.pi * 440 * t), SAMPLE_RATE

    def generate_stream(
        self,
        text: str,
        language: str = "English",
        chunk_size: int = 12,
    ) -> Generator[tuple[np.ndarray, int]]:
        samples, sr = self.generate(text, language)
        chunk_samples = max(1, int(sr * chunk_size / _TOKEN_RATE))
        for i in range(0, len(samples), chunk_samples):
            yield samples[i : i + chunk_samples], sr


_DEFAULT_SPEAKER = "ryan"


class QwenTTSEngine:
    """Official qwen-tts backend. Supports MPS and CUDA. No token-level streaming."""

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        device: str = "auto",
        **_kwargs,
    ):
        import torch
        from qwen_tts import Qwen3TTSModel

        if device == "auto":
            if torch.cuda.is_available():
                device = "cuda:0"
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"

        self._device = device
        self._model = Qwen3TTSModel.from_pretrained(
            model_name,
            device_map=device,
            dtype=torch.bfloat16,
        )

    def generate(self, text: str, language: str = "English") -> tuple[np.ndarray, int]:
        wavs, sr = self._model.generate_custom_voice(
            text=text, speaker=_DEFAULT_SPEAKER, language=language,
        )
        return np.concatenate(wavs).astype(np.float32), sr

    def generate_stream(
        self,
        text: str,
        language: str = "English",
        chunk_size: int = 12,
    ) -> Generator[tuple[np.ndarray, int]]:
        samples, sr = self.generate(text, language)
        chunk_samples = max(1, int(sr * chunk_size / _TOKEN_RATE))
        for i in range(0, len(samples), chunk_samples):
            yield samples[i : i + chunk_samples], sr


class FasterQwenTTSEngine:
    """faster-qwen3-tts backend. CUDA only. True token-level streaming."""

    def __init__(self, model_name: str = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice", **_kwargs):
        from faster_qwen3_tts import FasterQwen3TTS

        self._model = FasterQwen3TTS.from_pretrained(model_name)

    def generate(self, text: str, language: str = "English") -> tuple[np.ndarray, int]:
        wavs, sr = self._model.generate_custom_voice(
            text=text, speaker=_DEFAULT_SPEAKER, language=language,
        )
        return np.concatenate(wavs).astype(np.float32), sr

    def generate_stream(
        self,
        text: str,
        language: str = "English",
        chunk_size: int = 12,
    ) -> Generator[tuple[np.ndarray, int]]:
        for audio_chunk, sr, _timing in self._model.generate_custom_voice_streaming(
            text=text,
            speaker=_DEFAULT_SPEAKER,
            language=language,
            chunk_size=chunk_size,
        ):
            yield audio_chunk.astype(np.float32), sr


_BACKENDS = {
    "mock": MockEngine,
    "qwen": QwenTTSEngine,
    "faster": FasterQwenTTSEngine,
}


def create_engine(
    backend: str | None = None,
    model_name: str = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    **kwargs,
) -> TTSEngine:
    if backend is None:
        backend = os.environ.get("QWEN_TTS_ENGINE", "qwen")
    if backend not in _BACKENDS:
        raise ValueError(f"Unknown backend {backend!r}. Valid choices: {list(_BACKENDS)}")
    cls = _BACKENDS[backend]
    if cls is MockEngine:
        return cls()
    return cls(model_name=model_name, **kwargs)
