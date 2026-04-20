<h1 align="center">qwen-tts-serve</h1>

<p align="center">
  <strong>Real-time streaming Qwen3-TTS over WebSocket</strong>
</p>

<p align="center">
  <a href="https://github.com/CallumJMac/qwen-tts-serve/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=for-the-badge" alt="License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
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
uv sync --extra server --extra dev

# Start server (Mac - downloads 0.6B model on first run)
uv run uvicorn qwen_tts_serve.server:app --host 0.0.0.0 --port 8000

# Run demo (in another terminal)
uv run scripts/demo.py

# Stream from a remote server and play in real time
export QWEN_TTS_URL=ws://YOUR_ALB/ws/tts
python scripts/stream_demo.py "Hello world"
```

## GPU Deployment

```bash
# Install with CUDA acceleration
uv sync --extra cuda --extra server --extra dev

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

## Voice Cloning

The server supports voice cloning when using the Base model (`Qwen3-TTS-12Hz-0.6B-Base`). Register a reference voice, then use it for all subsequent requests.

```bash
# Register a voice (provide 5-30s reference audio + transcript)
curl -X POST http://YOUR_SERVER/voices \
  -F "voice_id=my_voice" \
  -F "ref_text=Transcript of the reference audio." \
  -F "ref_audio=@reference.wav"

# Stream with the cloned voice (pass voice_id in the WebSocket request)
{"text": "Hello world", "voice_id": "my_voice"}
```

Interactive demo with real-time playback:

```bash
python scripts/voice_clone_demo.py \
  --ref-audio reference.wav \
  --ref-text "Transcript of the reference audio." \
  --voice-id my_voice \
  "Text to speak in the cloned voice"
```

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
| 1 - Local | Server + client + demo with 0.6B on Mac | ✅ Done |
| 2 - Deploy | Dockerfile + Terraform + GPU on g5.xlarge (A10G) | ✅ Done |
| 3 - Integrate | Voice-loop `--tts-backend qwen` drop-in adapter | ✅ Done |
| 4 - Real-time | True token-level streaming via `faster-qwen3-tts` | ✅ Done |

## Performance

Deployed on g5.xlarge (A10G, 24 GB VRAM) with `faster-qwen3-tts` (CUDA graph acceleration):

| Metric | Before (Phase 3) | After (Phase 4) |
|--------|------------------|-----------------|
| First audio (TTFA) | ~10 s | **~500 ms** |
| Real-time factor | 1.8× (slower than real-time) | **0.5×** (2× faster than real-time) |
| Streaming | Batch then slice | True token-level |
| Cold start | ~15 s on first request | None (warm-up at startup) |

## License

Apache 2.0
