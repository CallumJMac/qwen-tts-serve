from __future__ import annotations

import json
import logging
import os

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from qwen_tts_serve.engine import create_engine

logger = logging.getLogger(__name__)

app = FastAPI(title="qwen-tts-serve")

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        model = os.environ.get("QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-Base")
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

        for chunk, sr in engine.generate_stream(text, language=language, chunk_size=chunk_size):
            await ws.send_bytes(chunk.astype(np.float32).tobytes())
            total_samples += len(chunk)

        await ws.send_text(json.dumps({"done": True, "total_samples": total_samples}))
    except WebSocketDisconnect:
        logger.info("Client disconnected (barge-in or cancel)")
    except Exception as e:
        logger.exception("TTS generation failed")
        try:
            await ws.send_text(json.dumps({"error": str(e)}))
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
