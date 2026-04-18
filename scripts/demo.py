#!/usr/bin/env python3
"""End-to-end demo: start server, stream TTS, play audio through speakers."""
from __future__ import annotations

import subprocess
import sys
import time

import numpy as np
import sounddevice as sd

from qwen_tts_serve.client import QwenTTSClient

SAMPLE_RATE = 24000
SERVER_CMD = [
    sys.executable, "-m", "uvicorn",
    "qwen_tts_serve.server:app",
    "--host", "127.0.0.1", "--port", "8000",
]
TEXT = "This is a test of the Qwen three text to speech streaming server."


def wait_for_server(url: str, timeout: float = 120):
    import urllib.request
    health = url.replace("ws://", "http://").replace("/ws/tts", "/health")
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            urllib.request.urlopen(health, timeout=2)
            return
        except Exception:
            time.sleep(1)
    raise TimeoutError(f"Server did not start within {timeout}s")


def main():
    print("Starting server...", flush=True)
    proc = subprocess.Popen(SERVER_CMD, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        url = "ws://127.0.0.1:8000/ws/tts"
        wait_for_server(url)
        print("Server ready. Streaming audio...\n", flush=True)

        client = QwenTTSClient(url)
        stream = sd.OutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32")
        stream.start()

        total = 0
        for chunk, sr in client.create_stream(TEXT):
            stream.write(chunk.reshape(-1, 1))
            total += len(chunk)
            dur = total / sr
            print(f"\r  Played {dur:.1f}s", end="", flush=True)

        stream.stop()
        stream.close()
        print(f"\n\nDone — {total / SAMPLE_RATE:.1f}s of audio streamed.", flush=True)
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
