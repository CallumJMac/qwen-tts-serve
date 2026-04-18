FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
# uv installs Python 3.14 automatically from python-build-standalone
RUN uv sync --frozen --extra cuda --no-dev --python 3.14

COPY src/ src/

EXPOSE 8000

ENV QWEN_TTS_ENGINE=faster
ENV QWEN_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice

CMD ["uv", "run", "uvicorn", "qwen_tts_serve.server:app", "--host", "0.0.0.0", "--port", "8000"]
