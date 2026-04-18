from __future__ import annotations

import asyncio
import json
import logging
import os

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from qwen_tts_serve.engine import create_engine

logger = logging.getLogger(__name__)

app = FastAPI(title="qwen-tts-serve")

_engine = None


# NOTE: not thread-safe — intended for single-worker deployment only (v1).
def _get_engine():
    global _engine
    if _engine is None:
        model = os.environ.get("QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
        _engine = create_engine(model_name=model)
    return _engine


@app.get("/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws/tts")
async def ws_tts(ws: WebSocket):
    await ws.accept()
    try:
        raw = await ws.receive_text()
        req = json.loads(raw)
        text = req.get("text")
        if not text:
            await ws.send_text(json.dumps({"error": "missing 'text' field"}))
            await ws.close()
            return

        language = req.get("language", "English")
        chunk_size = req.get("chunk_size", 12)
        engine = _get_engine()
        total_samples = 0
        sample_rate = 24000

        # Run the blocking generator in a thread pool to avoid stalling the event loop.
        # StopIteration cannot cross a Future boundary, so we use a sentinel wrapper.
        _DONE = object()

        def _next(gen):
            try:
                return next(gen)
            except StopIteration:
                return _DONE

        loop = asyncio.get_event_loop()
        gen = engine.generate_stream(text, language=language, chunk_size=chunk_size)
        while True:
            result = await loop.run_in_executor(None, _next, gen)
            if result is _DONE:
                break
            chunk, sample_rate = result
            await ws.send_bytes(chunk.astype(np.float32).tobytes())
            total_samples += len(chunk)

        done_msg = {"done": True, "total_samples": total_samples, "sample_rate": sample_rate}
        await ws.send_text(json.dumps(done_msg))
    except WebSocketDisconnect:
        logger.info("Client disconnected (barge-in or cancel)")
    except Exception as e:
        logger.exception("TTS generation failed")
        try:
            await ws.send_text(json.dumps({"error": str(e)}))
        except Exception:
            pass
