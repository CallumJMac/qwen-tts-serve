#!/usr/bin/env python3
"""Register a cloned voice and stream TTS with it."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time

import numpy as np
import requests
import sounddevice as sd
import websockets

SAMPLE_RATE = 24000
DEFAULT_URL = os.environ.get("QWEN_TTS_URL", "ws://localhost:8000/ws/tts")


def register_voice(base_url: str, voice_id: str, ref_audio: str, ref_text: str):
    http_url = base_url.replace("ws://", "http://").replace("wss://", "https://")
    http_url = http_url.split("/ws/")[0]
    url = f"{http_url}/voices"

    with open(ref_audio, "rb") as f:
        resp = requests.post(
            url,
            data={"voice_id": voice_id, "ref_text": ref_text},
            files={"ref_audio": (os.path.basename(ref_audio), f, "audio/wav")},
        )
    resp.raise_for_status()
    print(f"  Voice '{voice_id}' registered.")
    return resp.json()


async def stream_and_play(url: str, text: str, voice_id: str, chunk_size: int):
    print(f'  "{text}"\n')

    stream = sd.OutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    stream.start()
    start = time.time()
    first_chunk_t = None
    total_samples = 0

    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({
            "text": text,
            "language": "English",
            "chunk_size": chunk_size,
            "voice_id": voice_id,
        }))

        while True:
            msg = await ws.recv()
            now = time.time()

            if isinstance(msg, bytes):
                samples = np.frombuffer(msg, dtype=np.float32)
                stream.write(samples.reshape(-1, 1))
                total_samples += len(samples)
                if first_chunk_t is None:
                    first_chunk_t = now - start
                    print(f"  First audio: {first_chunk_t:.3f}s")
                print(f"\r  Playing: {total_samples / SAMPLE_RATE:.1f}s", end="", flush=True)
            else:
                data = json.loads(msg)
                if "done" in data:
                    gen_time = now - start
                    dur = data["total_samples"] / data["sample_rate"]
                    print(f"\r  Playing: {dur:.1f}s  (generated in {gen_time:.1f}s, RTF {gen_time/dur:.2f}x)")
                    remaining = dur - gen_time
                    if remaining > 0:
                        await asyncio.sleep(remaining + 0.1)
                    break
                elif "error" in data:
                    print(f"\n  Error: {data['error']}")
                    break

    stream.stop()
    stream.close()
    print("  Done.")


def main():
    parser = argparse.ArgumentParser(description="Clone a voice and stream TTS")
    parser.add_argument("--ref-audio", required=True, help="Path to reference audio file")
    parser.add_argument("--ref-text", required=True, help="Transcript of reference audio")
    parser.add_argument("--voice-id", default="cloned", help="Name for the cloned voice")
    parser.add_argument("text", help="Text to speak in the cloned voice")
    parser.add_argument("--url", default=DEFAULT_URL, help="WebSocket URL")
    parser.add_argument("--chunk-size", type=int, default=4, help="Codec tokens per chunk")
    args = parser.parse_args()

    print("\nRegistering voice...")
    register_voice(args.url, args.voice_id, args.ref_audio, args.ref_text)

    print("\nStreaming...")
    asyncio.run(stream_and_play(args.url, args.text, args.voice_id, args.chunk_size))


if __name__ == "__main__":
    main()
