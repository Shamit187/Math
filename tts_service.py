"""
tts_service.py — TTS backend for Slow Books.

Detects hardware at startup:
  - CUDA or MPS  →  downloads the Kokoro-82M model to ROOT/tts/ and serves audio
  - CPU only     →  TTS disabled (no synthesis endpoint available)

The model is loaded in a background thread so the server is never blocked.
Install deps with:  pip install kokoro soundfile
"""
import io
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_state: dict = {
    "enabled": False,
    "device": "cpu",
    "state": "disabled",    # disabled | initializing | ready | error
    "message": "TTS service not started",
}
_pipeline = None
_lock = threading.Lock()
_tts_dir: Path | None = None


# ---------- hardware detection ----------

def _detect_device() -> str:
    # Authoritative check via torch when it's installed
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    except ImportError:
        pass

    # torch not installed — fall back to platform heuristics
    import platform
    import sys
    if sys.platform == "darwin" and platform.machine() == "arm64":
        # Apple Silicon (M1/M2/M3/M4) always has Metal GPU → MPS
        return "mps"
    return "cpu"


# ---------- public API ----------

def init(tts_dir: Path) -> None:
    """Call once at server startup. Non-blocking — model loads in a daemon thread."""
    global _tts_dir
    _tts_dir = tts_dir
    tts_dir.mkdir(parents=True, exist_ok=True)

    device = _detect_device()
    with _lock:
        _state["device"] = device

    if device == "cpu":
        with _lock:
            _state.update({
                "enabled": False,
                "state": "disabled",
                "message": "TTS requires MPS or CUDA — CPU-only hardware detected.",
            })
        logger.info("[TTS] %s", _state["message"])
        return

    with _lock:
        _state.update({
            "state": "initializing",
            "message": (
                f"Loading TTS model on {device} "
                "(first run downloads ~350 MB to tts/ folder)…"
            ),
        })

    threading.Thread(target=_load_model, args=(device,), daemon=True).start()
    threading.Thread(target=_watch_init, daemon=True).start()


def _watch_init() -> None:
    """Poll until the model is ready or failed, then print a clear status line."""
    import time
    while True:
        time.sleep(0.5)
        with _lock:
            state = _state["state"]
            msg = _state["message"]
        if state == "ready":
            print(f"\n[TTS] {msg}\n", flush=True)
            return
        if state in ("error", "disabled"):
            print(f"\n[TTS] {msg}\n", flush=True)
            return


def get_status() -> dict:
    with _lock:
        return dict(_state)


def synthesize(text: str, speed: float = 1.0) -> bytes:
    """Return raw WAV bytes for *text*. Raises RuntimeError when TTS is not ready."""
    with _lock:
        pipeline = _pipeline

    if pipeline is None:
        raise RuntimeError("TTS not ready")

    speed = max(0.5, min(2.0, speed))

    import wave
    import numpy as np          # type: ignore

    chunks = []
    for _gs, _ps, audio in pipeline(text, voice="af_heart", speed=speed):
        chunks.append(audio)

    if not chunks:
        raise RuntimeError("TTS produced no audio")

    full = np.concatenate(chunks)
    # Convert float32 [-1, 1] → int16 PCM for a standard WAV file
    pcm = (np.clip(full, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)      # 16-bit
        wf.setframerate(24000)
        wf.writeframes(pcm.tobytes())
    buf.seek(0)
    return buf.read()


# ---------- background loader ----------

def _load_model(device: str) -> None:
    global _pipeline
    try:
        # Redirect HuggingFace downloads into the project's tts/ folder
        os.environ.setdefault("HF_HOME", str(_tts_dir))
        # Silence "unauthenticated requests" noise from huggingface_hub
        os.environ.setdefault("HF_HUB_VERBOSITY", "error")

        import warnings
        # Suppress known harmless torch warnings from the Kokoro model weights
        warnings.filterwarnings("ignore", message=".*dropout option adds dropout.*", category=UserWarning)
        warnings.filterwarnings("ignore", message=".*weight_norm.*deprecated.*", category=FutureWarning)

        logger.info("[TTS] Importing kokoro…")
        from kokoro import KPipeline  # type: ignore

        logger.info("[TTS] Building pipeline on %s (downloading model if needed)…", device)
        pipeline = KPipeline(lang_code="a", device=device, repo_id="hexgrad/Kokoro-82M")

        with _lock:
            _pipeline = pipeline
            _state.update({
                "enabled": True,
                "state": "ready",
                "message": f"TTS ready on {device}",
            })
        logger.info("[TTS] %s", _state["message"])

    except ImportError:
        msg = (
            "TTS disabled: 'kokoro' package not found. "
            "Install with:  pip install kokoro soundfile"
        )
        with _lock:
            _state.update({"enabled": False, "state": "error", "message": msg})
        logger.warning("[TTS] %s", msg)

    except Exception as exc:
        msg = f"TTS initialization failed: {exc}"
        with _lock:
            _state.update({"enabled": False, "state": "error", "message": msg})
        logger.error("[TTS] %s", msg, exc_info=True)
