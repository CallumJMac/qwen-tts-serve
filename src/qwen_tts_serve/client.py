from __future__ import annotations

import json
from collections.abc import Generator

import numpy as np
from websockets.sync.client import connect

SAMPLE_RATE = 24000


class QwenTTSClient:
    def __init__(self, url: str = "ws://localhost:8000/ws/tts"):
        self._url = url

    def create(
        self,
        text: str,
        voice: str = "default",
        speed: float = 1.0,
        lang: str = "en-us",
    ) -> tuple[np.ndarray, int]:
        chunks = list(self.create_stream(text, voice=voice, speed=speed, lang=lang))
        if not chunks:
            return np.array([], dtype=np.float32), SAMPLE_RATE
        arrays = [c for c, _sr in chunks]
        return np.concatenate(arrays), chunks[0][1]

    def create_stream(
        self,
        text: str,
        voice: str = "default",
        speed: float = 1.0,
        lang: str = "en-us",
    ) -> Generator[tuple[np.ndarray, int]]:
        with connect(self._url) as ws:
            ws.send(json.dumps({"text": text, "voice": voice, "language": "English"}))
            while True:
                msg = ws.recv()
                if isinstance(msg, bytes):
                    chunk = np.frombuffer(msg, dtype=np.float32).copy()
                    yield chunk, SAMPLE_RATE
                else:
                    data = json.loads(msg)
                    if data.get("done"):
                        break
                    if "error" in data:
                        raise RuntimeError(data["error"])
