"""
tts_service.py — TTS backend for Slow Books.

Detects hardware at startup:
  - CUDA or MPS  →  downloads the Kokoro-82M model to ROOT/tts/ and serves audio
  - CPU only     →  TTS disabled (no synthesis endpoint available)

The default pipeline (American English, lang_code="a") loads at startup in a
daemon thread. Additional pipelines for other language codes (e.g. "b" for
British English) are loaded lazily on first use.

Install deps with:  pip install kokoro soundfile
"""
import io
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Curated voice catalog. Each entry maps a Kokoro voice ID to its display label,
# its language code (which selects the pipeline), and its quality grade.
VOICES: list[dict] = [
    {"id": "af_heart",  "label": "Heart, Neutral",        "lang": "a", "grade": "A"},
    {"id": "af_bella",  "label": "Bella, Charming",        "lang": "a", "grade": "A-"},
    {"id": "af_sky",    "label": "Sky, Mature",   "lang": "a", "grade": "B+"},
    {"id": "af_nicole", "label": "Nicole, ASMR",       "lang": "a", "grade": "B-"},
    {"id": "bf_emma",   "label": "Emma, British",         "lang": "b", "grade": "B-"},
]
DEFAULT_VOICE = "af_heart"
DEFAULT_LANG = "a"

_state: dict = {
    "enabled": False,
    "device": "cpu",
    "state": "disabled",    # disabled | initializing | ready | error
    "message": "TTS service not started",
}
_pipelines: dict = {}              # lang_code → KPipeline
_pipeline_locks: dict = {}         # lang_code → threading.Lock (creation lock)
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

    threading.Thread(target=_load_default_pipeline, args=(device,), daemon=True).start()
    threading.Thread(target=_watch_init, daemon=True).start()


def _watch_init() -> None:
    """Poll until the default pipeline is ready or failed, then print status."""
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


def list_voices() -> list[dict]:
    """Public voice catalog returned to the frontend."""
    return [
        {"id": v["id"], "label": v["label"], "grade": v["grade"], "lang": v["lang"]}
        for v in VOICES
    ]


def _voice_info(voice: str) -> dict:
    for v in VOICES:
        if v["id"] == voice:
            return v
    # Unknown voice → fall back to default
    for v in VOICES:
        if v["id"] == DEFAULT_VOICE:
            return v
    return VOICES[0]


def _get_pipeline(lang_code: str):
    """Return a ready pipeline for *lang_code*, lazy-loading if needed.

    Returns None when the service isn't enabled or loading fails.
    Blocks while a pipeline for *lang_code* is being loaded.
    """
    if lang_code in _pipelines:
        return _pipelines[lang_code]

    with _lock:
        if not _state["enabled"]:
            return None
        device = _state["device"]
        creation_lock = _pipeline_locks.setdefault(lang_code, threading.Lock())

    with creation_lock:
        if lang_code in _pipelines:
            return _pipelines[lang_code]
        try:
            from kokoro import KPipeline  # type: ignore
            logger.info("[TTS] Lazy-loading pipeline for lang_code=%s on %s", lang_code, device)
            pipe = KPipeline(lang_code=lang_code, device=device, repo_id="hexgrad/Kokoro-82M")
            _pipelines[lang_code] = pipe
            return pipe
        except Exception as exc:
            logger.error("[TTS] Failed to load pipeline for lang_code=%s: %s", lang_code, exc, exc_info=True)
            return None


def synthesize(text: str, voice: str = DEFAULT_VOICE, speed: float = 1.0) -> bytes:
    """Return raw WAV bytes for *text* using *voice*. Raises RuntimeError when not ready."""
    info = _voice_info(voice)
    pipeline = _get_pipeline(info["lang"])
    if pipeline is None:
        raise RuntimeError(f"TTS pipeline for language '{info['lang']}' not ready")

    speed = max(0.5, min(2.0, speed))

    import wave
    import numpy as np          # type: ignore

    chunks = []
    for _gs, _ps, audio in pipeline(text, voice=info["id"], speed=speed):
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

def _load_default_pipeline(device: str) -> None:
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

        logger.info("[TTS] Building default pipeline (lang=%s) on %s…", DEFAULT_LANG, device)
        pipeline = KPipeline(lang_code=DEFAULT_LANG, device=device, repo_id="hexgrad/Kokoro-82M")

        with _lock:
            _pipelines[DEFAULT_LANG] = pipeline
            _state.update({
                "enabled": True,
                "state": "ready",
                "message": f"TTS ready on {device} ({len(VOICES)} voices available)",
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
