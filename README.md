<h1 align="center">qwen-tts-serve</h1>

<p align="center">
  <strong>Low-latency streaming Qwen3-TTS over WebSocket</strong>
</p>

<p align="center">
  <a href="https://github.com/CallumJMac/qwen-tts-serve/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=for-the-badge" alt="License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
</p>

`qwen-tts-serve` wraps Qwen3-TTS in a small FastAPI service and streams 24 kHz
float32 PCM audio over WebSocket. It supports local development with the official
`qwen-tts` backend and true token-level streaming on NVIDIA GPUs with
[`faster-qwen3-tts`](https://github.com/andimarafioti/faster-qwen3-tts).

## Features

- True token-level streaming with CUDA graph acceleration
- CustomVoice and prompt-based voice cloning models
- Lightweight Python client with blocking and streaming APIs
- Docker image with model weights downloaded at build time
- Terraform deployment to ECS on GPU-backed EC2
- Startup warm-up and readiness health check

## Architecture

```text
Python client or voice agent
            │
            │ WebSocket
            ▼
       FastAPI server
            │
            ├── qwen-tts: MPS, CUDA, or CPU; full generation then chunking
            └── faster-qwen3-tts: CUDA; true token-level streaming
```

## Quick start

Install [uv](https://docs.astral.sh/uv/), clone the repository, and start the
official backend:

```bash
git clone https://github.com/CallumJMac/qwen-tts-serve.git
cd qwen-tts-serve
uv sync --extra server --extra dev

uv run uvicorn qwen_tts_serve.server:app \
  --host 0.0.0.0 \
  --port 8000
```

The model downloads on first startup. In another terminal:

```bash
uv run python scripts/stream_demo.py "Hello world"
```

The official backend returns chunks only after generating the complete utterance.
Use the CUDA backend for low-latency streaming.

## CUDA streaming

The accelerated backend requires an NVIDIA GPU and CUDA:

```bash
uv sync --extra cuda --extra server --extra dev

QWEN_TTS_ENGINE=faster \
uv run uvicorn qwen_tts_serve.server:app \
  --host 0.0.0.0 \
  --port 8000
```

The server warms the model before `/health` returns `200`, so CUDA graph capture
does not delay the first user request.

### Configuration

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `QWEN_TTS_ENGINE` | `qwen` | `qwen`, `faster`, or `mock` |
| `QWEN_TTS_MODEL` | `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` | Hugging Face model ID |
| `URL_PREFIX` | empty | Optional prefix for all HTTP and WebSocket routes |

## Client library

```python
from qwen_tts_serve.client import QwenTTSClient

client = QwenTTSClient("ws://localhost:8000/ws/tts")

# Collect the complete waveform.
samples, sample_rate = client.create("Hello world")

# Process chunks as they arrive.
for chunk, sample_rate in client.create_stream("Hello world", chunk_size=4):
    play(chunk)
```

The client depends only on `websockets` and `numpy`.

## WebSocket protocol

The client sends one JSON request:

```json
{
  "text": "Hello world",
  "language": "English",
  "chunk_size": 4,
  "voice_id": "optional-cloned-voice"
}
```

The server responds with binary float32 PCM chunks at 24 kHz, followed by:

```json
{
  "done": true,
  "total_samples": 48000,
  "sample_rate": 24000
}
```

Closing the WebSocket stops delivery to the client. Immediate cancellation of
in-flight GPU work is not guaranteed.

## Voice cloning

Voice cloning requires the Base model:

```bash
QWEN_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-Base \
QWEN_TTS_ENGINE=faster \
uv run uvicorn qwen_tts_serve.server:app --host 0.0.0.0 --port 8000
```

Register a 5 to 30 second reference clip and its transcript:

```bash
curl -X POST http://localhost:8000/voices \
  -F "voice_id=my_voice" \
  -F "ref_text=Transcript of the reference audio." \
  -F "ref_audio=@reference.wav"
```

Then pass `"voice_id": "my_voice"` in the WebSocket request, or run:

```bash
uv run python scripts/voice_clone_demo.py \
  --ref-audio reference.wav \
  --ref-text "Transcript of the reference audio." \
  --voice-id my_voice \
  "Text to speak in the cloned voice"
```

Registered voices are stored on local ephemeral disk and are not shared across
replicas.

## Deploy to AWS

The Terraform stack provisions ECR, ECS on `g5.xlarge` instances, and an
Application Load Balancer with separate routes for CustomVoice and voice cloning.

```bash
cd infra
terraform init
terraform apply -target=aws_ecr_repository.this
cd ..

AWS_PROFILE=your-profile AWS_REGION=us-east-1 ./scripts/deploy.sh
```

The deployment exposes:

- `ws://<alb>/custom/ws/tts`
- `ws://<alb>/clone/ws/tts`

The example stack uses plain HTTP and WebSocket. Add TLS and authentication before
exposing it to untrusted traffic.

## Performance

Measurements used Qwen3-TTS 0.6B CustomVoice on one AWS `g5.xlarge` with an
NVIDIA A10G 24 GB. Each value is the p50 from 30 recorded runs after three
warm-ups; ranges cover short, medium, and long prompts.

| Path | TTFA p50 | RTF p50 |
| --- | ---: | ---: |
| Official `qwen-tts`, full generation | n/a | 1.70 to 1.71 |
| `faster-qwen3-tts`, full generation | n/a | 0.35 to 0.36 |
| Deployed streaming endpoint through ALB | 187 to 189 ms | 0.44 to 0.45 |

Real-time factor (RTF) is wall-clock synthesis time divided by generated audio
duration. Lower is better: `1.0` is real time, while `0.35` produces about 2.86
seconds of audio per wall-clock second.

The CUDA full-generation path was approximately 4.7 to 4.9 times faster by RTF.
The official and optimized engines produced outputs with different durations, so
this is not an identical-output comparison. Streaming increases RTF slightly
because decoding small chunks trades throughput for earlier audio.

For methodology, audio samples, and limitations, see:

- [How to Build a Low-Latency Streaming Qwen3-TTS Server](https://callumjmac.github.io/posts/qwen-tts-streaming/)
- [Capacity Planning Qwen3-TTS on an A10G](https://callumjmac.github.io/posts/qwen-tts-at-scale/)

## Current limitations

- The server uses an application-scoped model instance and is intended for a
  single Uvicorn worker.
- Concurrent generation is not safely supported by the current engine.
- Voice references use ephemeral local storage.
- Closing a client connection does not prove immediate cancellation of GPU work.
- The included AWS stack does not configure TLS or authentication.

## Development

Tests use a deterministic mock engine and do not require a GPU:

```bash
uv sync --extra server --extra dev
uv run pytest
uv run ruff check .
```

## License

Apache 2.0
