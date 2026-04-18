<h1 align="center">qwen-tts-serve</h1>

<p align="center">
  <strong>Real-time streaming Qwen3-TTS over WebSocket</strong>
</p>

<p align="center">
  <a href="https://github.com/CallumJMac/qwen-tts-serve/actions"><img src="https://img.shields.io/github/actions/workflow/status/CallumJMac/qwen-tts-serve/ci.yml?branch=main&style=for-the-badge" alt="CI"></a>
  <a href="https://github.com/CallumJMac/qwen-tts-serve/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=for-the-badge" alt="License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.14+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
</p>

<p align="center">
  Stream Qwen3-TTS audio chunks in real time over WebSocket.<br>
  Local dev on Mac (MPS) &bull; GPU deployment to AWS (CUDA) &bull; Drop-in replacement for Kokoro TTS.
</p>

---

## Architecture

```
Client (voice-loop, CLI)          Server (FastAPI)
┌────────────────────┐            ┌──────────────────────┐
│                    │  WebSocket  │                      │
│  QwenTTSClient     │◄──────────►│  /ws/tts             │
│                    │ binary PCM  │                      │
│  .create()         │  chunks     │  Engine abstraction  │
│  .create_stream()  │            │  ├─ qwen-tts (MPS)   │
│                    │            │  └─ faster-qwen3-tts  │
└────────────────────┘            │      (CUDA)           │
                                  └──────────────────────┘
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
| 1 — Local | Server + client + demo with 0.6B on Mac | Current |
| 2 — Deploy | Dockerfile + Terraform + 1.7B on g5.xlarge | Planned |
| 3 — Integrate | Voice-loop adapter + voice cloning | Planned |

## License

Apache 2.0
