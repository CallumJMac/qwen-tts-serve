import json
import os

import numpy as np
from starlette.testclient import TestClient

os.environ["QWEN_TTS_ENGINE"] = "mock"

from qwen_tts_serve.server import app


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ws_tts_returns_audio_then_done():
    client = TestClient(app)
    with client.websocket_connect("/ws/tts") as ws:
        ws.send_json({"text": "Hello world", "voice": "default"})
        chunks = []
        while True:
            msg = ws.receive()
            if "text" in msg:
                data = json.loads(msg["text"])
                assert data["done"] is True
                assert "total_samples" in data
                break
            elif "bytes" in msg:
                chunk = np.frombuffer(msg["bytes"], dtype=np.float32)
                chunks.append(chunk)
        assert len(chunks) >= 1
        total = sum(len(c) for c in chunks)
        assert total > 0


def test_ws_tts_missing_text_returns_error():
    client = TestClient(app)
    with client.websocket_connect("/ws/tts") as ws:
        ws.send_json({"voice": "default"})
        msg = ws.receive()
        data = json.loads(msg["text"])
        assert "error" in data
