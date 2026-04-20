#!/usr/bin/env python3
"""Stream TTS from a remote server and play audio as chunks arrive."""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import numpy as np
import sounddevice as sd
import websockets


SAMPLE_RATE = 24000
DEFAULT_URL = "ws://qwen-tts-serve-10958726.us-east-1.elb.amazonaws.com/ws/tts"
DEFAULT_TEXT = (
    "This is an example of the Qwen TTS server streaming audio in real time."
)


async def stream_and_play(url: str, text: str, chunk_size: int):
    print(f'  "{text}"\n')

    stream = sd.OutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    stream.start()
    start = time.time()
    first_chunk_t = None
    total_samples = 0

    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({"text": text, "language": "English", "chunk_size": chunk_size}))

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
    parser = argparse.ArgumentParser(description="Stream TTS and play in real time")
    parser.add_argument("text", nargs="?", default=DEFAULT_TEXT, help="Text to speak")
    parser.add_argument("--url", default=DEFAULT_URL, help="WebSocket URL")
    parser.add_argument("--chunk-size", type=int, default=4, help="Codec tokens per chunk (lower = less latency)")
    args = parser.parse_args()
    asyncio.run(stream_and_play(args.url, args.text, args.chunk_size))


if __name__ == "__main__":
    main()
