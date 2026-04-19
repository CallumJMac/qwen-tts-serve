<h1 align="center">qwen-tts-serve</h1>

<p align="center">
  <strong>Real-time streaming Qwen3-TTS over WebSocket</strong>
</p>

<p align="center">
  <a href="https://github.com/CallumJMac/qwen-tts-serve/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=for-the-badge" alt="License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
</p>

<p align="center">
  Stream Qwen3-TTS audio chunks in real time over WebSocket.<br>
  Local dev on Mac (MPS) &bull; GPU deployment to AWS (CUDA) &bull; Drop-in replacement for Kokoro TTS.
</p>

---

## Architecture

```
Client (voice-loop, CLI)               Server (FastAPI)
┌──────────────────────┐               ┌──────────────────────────┐
│  QwenTTSClient       │   WebSocket   │  /ws/tts                 │
│                      │◄─────────────►│                          │
│  .create()           │  float32 PCM  │  Engine abstraction      │
│  .create_stream()    │    chunks     │  ├─ qwen-tts  (MPS/CPU)  │
│                      │               │  └─ faster-qwen3-tts     │
└──────────────────────┘               │        (CUDA)            │
                                       └──────────────────────────┘
```

## Quick Start

```bash
# Install
git clone https://github.com/CallumJMac/qwen-tts-serve.git
cd qwen-tts-serve
uv sync --extra dev

# Start server (Mac — downloads 0.6B model on first run)
uv run uvicorn qwen_tts_serve.server:app --host 0.0.0.0 --port 8000

# Run demo (in another terminal)
uv run scripts/demo.py
```

## GPU Deployment

```bash
# Install with CUDA acceleration
uv sync --extra cuda --extra dev

# Start server with faster-qwen3-tts backend
QWEN_TTS_ENGINE=faster uv run uvicorn qwen_tts_serve.server:app --host 0.0.0.0 --port 8000
```

## Deploy to AWS

```bash
cd infra
terraform init
terraform apply -var="aws_region=us-east-1"
```

Provisions ECR + ECS on g5.xlarge (A10G, 24GB VRAM) with ALB for WebSocket.

## WebSocket Protocol

```
Client → Server:  {"text": "Hello world", "voice": "default"}
Server → Client:  [binary: float32 PCM chunk, 24kHz mono]
Server → Client:  [binary: float32 PCM chunk, 24kHz mono]
...
Server → Client:  {"done": true, "total_samples": 48000}
```

Cancel by closing the connection. Server aborts inference immediately.

## Client Library

```python
from qwen_tts_serve.client import QwenTTSClient

client = QwenTTSClient("ws://localhost:8000/ws/tts")

# Blocking (Kokoro-compatible drop-in)
samples, sr = client.create("Hello world")

# Streaming (for voice agents)
for chunk, sr in client.create_stream("Hello world"):
    play(chunk)
```

## Phasing

| Phase | Scope | Status |
|-------|-------|--------|
| 1 — Local | Server + client + demo with 0.6B on Mac | ✅ Done |
| 2 — Deploy | Dockerfile + Terraform + GPU on g5.xlarge (A10G) | ✅ Done |
| 3 — Integrate | Voice-loop `--tts-backend qwen` drop-in adapter | ✅ Done |
| 4 — Real-time | True token-level streaming via `faster-qwen3-tts` | Planned |

## Roadmap: Real-Time Streaming (Phase 4)

Current performance: ~10s to generate 5.6s of audio (1.8× slower than real-time). Audio is generated in full before the first byte is sent.

To achieve true real-time (<1× RTF, first audio in ~1-2s):

- [ ] **Fix `faster-qwen3-tts` CUDA compatibility** — the `faster` backend supports token-level streaming via `generate_custom_voice_streaming()` but currently fails to load on the ECS AMI (NVIDIA driver 550, CUDA 12.4). Needs a cu124-compatible build of the `faster-qwen3-tts` native extensions.
- [ ] **Stream audio to client as tokens are decoded** — update `FasterQwenTTSEngine.generate_stream()` to yield chunks immediately rather than buffering. The WebSocket server already supports this pattern.
- [ ] **Client-side streaming playback** — update `QwenTTSClient.create_stream()` and the voice-loop adapter to start playing the first chunk while subsequent chunks are still being generated.
- [ ] **Warm model on startup** — load and warm the model at server startup (not on first request) to eliminate the ~15s cold-start latency on the first inference.

## License

Apache 2.0
