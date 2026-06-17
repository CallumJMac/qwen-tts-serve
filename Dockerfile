FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN uv sync --extra cuda --extra server --no-dev --python 3.13

ARG QWEN_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-Base
ENV QWEN_TTS_MODEL=${QWEN_TTS_MODEL}
RUN uv run --no-sync python -c "from huggingface_hub import snapshot_download; snapshot_download('${QWEN_TTS_MODEL}')"

ENV URL_PREFIX=""
ENV QWEN_TTS_ENGINE=faster

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "qwen_tts_serve.server:app", "--host", "0.0.0.0", "--port", "8000"]
