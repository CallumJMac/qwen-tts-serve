import numpy as np

from qwen_tts_serve.engine import create_engine


def test_create_engine_returns_engine():
    engine = create_engine(backend="mock")
    assert hasattr(engine, "generate")
    assert hasattr(engine, "generate_stream")


def test_mock_generate_returns_audio():
    engine = create_engine(backend="mock")
    samples, sr = engine.generate("Hello world", language="English")
    assert isinstance(samples, np.ndarray)
    assert samples.dtype == np.float32
    assert sr == 24000
    assert len(samples) > 0


def test_mock_generate_stream_yields_chunks():
    engine = create_engine(backend="mock")
    chunks = list(engine.generate_stream("Hello world", language="English"))
    assert len(chunks) >= 1
    for chunk, sr in chunks:
        assert isinstance(chunk, np.ndarray)
        assert chunk.dtype == np.float32
        assert sr == 24000
