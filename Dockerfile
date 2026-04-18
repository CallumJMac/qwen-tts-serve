FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.14 python3.14-venv python3-pip curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra cuda --no-dev

COPY src/ src/

EXPOSE 8000

ENV QWEN_TTS_ENGINE=faster
ENV QWEN_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-Base

CMD ["uv", "run", "uvicorn", "qwen_tts_serve.server:app", "--host", "0.0.0.0", "--port", "8000"]
