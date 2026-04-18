import os
import threading

import numpy as np
import pytest
import uvicorn

os.environ["QWEN_TTS_ENGINE"] = "mock"

from qwen_tts_serve.server import app


@pytest.fixture(scope="module")
def server_url():
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)

    started = threading.Event()
    original_startup = server.startup

    actual_port = None

    async def patched_startup(sockets=None):
        await original_startup(sockets=sockets)
        nonlocal actual_port
        for s in server.servers:
            for sock in s.sockets:
                actual_port = sock.getsockname()[1]
                break
        started.set()

    server.startup = patched_startup
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    started.wait(timeout=5)
    yield f"ws://127.0.0.1:{actual_port}/ws/tts"
    server.should_exit = True
    thread.join(timeout=5)


def test_create_returns_audio(server_url):
    from qwen_tts_serve.client import QwenTTSClient

    client = QwenTTSClient(server_url)
    samples, sr = client.create("Hello world")
    assert isinstance(samples, np.ndarray)
    assert samples.dtype == np.float32
    assert sr == 24000
    assert len(samples) > 0


def test_create_stream_yields_chunks(server_url):
    from qwen_tts_serve.client import QwenTTSClient

    client = QwenTTSClient(server_url)
    chunks = list(client.create_stream("Hello world"))
    assert len(chunks) >= 1
    for chunk, sr in chunks:
        assert isinstance(chunk, np.ndarray)
        assert sr == 24000
