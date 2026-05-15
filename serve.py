"""
serve.py — the only command you need.

Hosts the entire Slow Books site (multi-book layout) AND the comments API
from a single Flask app at http://localhost:8765.

    python serve.py

Layout this server expects:

  ROOT/
    index.html              <- book index (homepage)
    css/, js/               <- shared static assets
    books/<book>/
      index.html            <- a book's home (chapter list)
      chapters/chNN.html    <- the actual content
    comments/comments.json  <- comment store, with {book, page, cid, text, ...}

Routing:

  /                          -> ROOT/index.html
  /<file>                    -> ROOT/<file>          (e.g. /css/style.css)
  /books/<book>/             -> ROOT/books/<book>/index.html
  /books/<book>/<path>       -> ROOT/books/<book>/<path>
  /api/health                -> healthcheck
  /api/books                 -> list of books detected on disk
  /api/comments              -> GET (filter by book and/or page), POST
  /api/comments/<id>         -> DELETE, PATCH
"""
import json
import logging
import sys
import time
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, abort, Response
from flask_cors import CORS

import tts_service

ROOT = Path(__file__).resolve().parent
COMMENTS_DIR = ROOT / "comments"
COMMENTS_FILE = COMMENTS_DIR / "comments.json"
HIGHLIGHTS_FILE = COMMENTS_DIR / "highlights.json"
NOTES_FILE = COMMENTS_DIR / "notes.json"
TTS_DIR = ROOT / "tts"
COMMENTS_DIR.mkdir(parents=True, exist_ok=True)

PORT = 8765

app = Flask(__name__, static_folder=None)
CORS(app)


# ---------- JSON storage helpers ----------
def _load_store(path: Path, key: str):
    if not path.exists():
        return {key: []}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault(key, [])
            return data
    except Exception:
        return {key: []}


def _save_store(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def _load():
    return _load_store(COMMENTS_FILE, "comments")


def _save(data):
    _save_store(COMMENTS_FILE, data)


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------- TTS API ----------
@app.route("/api/tts/status")
def tts_status():
    return jsonify(tts_service.get_status())


@app.route("/api/tts/voices")
def tts_voices():
    return jsonify({
        "voices": tts_service.list_voices(),
        "default": tts_service.DEFAULT_VOICE,
    })


@app.route("/api/tts/synthesize", methods=["POST"])
def tts_synthesize():
    status = tts_service.get_status()
    if not status["enabled"]:
        return jsonify({"error": "TTS not available", "detail": status["message"]}), 503
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    if len(text) > 6000:
        return jsonify({"error": "text too long (max 6000 chars)"}), 400
    try:
        raw_speed = body.get("speed", 1.0)
        try:
            speed = float(raw_speed)
        except (TypeError, ValueError):
            speed = 1.0
        voice = (body.get("voice") or tts_service.DEFAULT_VOICE).strip()
        audio_bytes = tts_service.synthesize(text, voice=voice, speed=speed)
        return Response(audio_bytes, mimetype="audio/wav")
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        logging.getLogger(__name__).error("TTS synthesis error: %s", exc, exc_info=True)
        return jsonify({"error": "synthesis failed"}), 500


# ---------- API ----------
@app.route("/api/health")
def health():
    return jsonify({"ok": True, "comments_file": str(COMMENTS_FILE)})


def _read_meta(path: Path) -> dict:
    """Read optional meta.json from a content directory."""
    meta_file = path / "meta.json"
    if meta_file.exists():
        try:
            return json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


@app.route("/api/books")
def list_books():
    out = []

    books_dir = ROOT / "books"
    if books_dir.exists():
        for d in sorted(books_dir.iterdir()):
            if not d.is_dir():
                continue
            meta = _read_meta(d)
            chapters = sorted((d / "chapters").glob("ch*.html")) if (d / "chapters").exists() else []
            out.append({
                "slug": d.name,
                "type": "book",
                "title": meta.get("title", d.name),
                "subtitle": meta.get("subtitle", ""),
                "description": meta.get("description", ""),
                "url": f"/books/{d.name}/",
                "n_chapters": len(chapters),
            })

    papers_dir = ROOT / "papers"
    if papers_dir.exists():
        for d in sorted(papers_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("_") or not (d / "index.html").exists():
                continue
            meta = _read_meta(d)
            out.append({
                "slug": d.name,
                "type": "paper",
                "title": meta.get("title", d.name),
                "subtitle": meta.get("subtitle", ""),
                "authors": meta.get("authors", ""),
                "venue": meta.get("venue", ""),
                "description": meta.get("description", ""),
                "url": f"/papers/{d.name}/",
            })

    return jsonify({"books": out})


@app.route("/api/comments", methods=["GET"])
def list_comments():
    book = request.args.get("book")
    page = request.args.get("page")
    data = _load()
    out = data["comments"]
    if book:
        out = [c for c in out if c.get("book") == book]
    if page:
        out = [c for c in out if c.get("page") == page]
    out = sorted(out, key=lambda c: c.get("created_at", ""))
    return jsonify({"comments": out})


@app.route("/api/comments", methods=["POST"])
def add_comment():
    body = request.get_json(silent=True) or {}
    book = (body.get("book") or "").strip()
    page = (body.get("page") or "").strip()
    cid = (body.get("cid") or "").strip()
    text = (body.get("text") or "").strip()
    excerpt = (body.get("block_excerpt") or "").strip()[:500]
    if not book or not page or not cid or not text:
        return jsonify({"error": "book, page, cid, and text are required"}), 400
    record = {
        "id": "c_" + uuid.uuid4().hex[:12],
        "book": book,
        "page": page,
        "cid": cid,
        "text": text,
        "block_excerpt": excerpt,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    data = _load()
    data["comments"].append(record)
    _save(data)
    return jsonify({"comment": record}), 201


@app.route("/api/comments/<cid>", methods=["DELETE"])
def delete_comment(cid):
    data = _load()
    before = len(data["comments"])
    data["comments"] = [c for c in data["comments"] if c.get("id") != cid]
    if len(data["comments"]) == before:
        return jsonify({"error": "not found"}), 404
    _save(data)
    return jsonify({"ok": True})


@app.route("/api/comments/<cid>", methods=["PATCH"])
def update_comment(cid):
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    data = _load()
    for c in data["comments"]:
        if c.get("id") == cid:
            c["text"] = text
            c["updated_at"] = _now_iso()
            _save(data)
            return jsonify({"comment": c})
    return jsonify({"error": "not found"}), 404


# ---------- highlights API ----------
def _load_highlights():
    return _load_store(HIGHLIGHTS_FILE, "highlights")


def _save_highlights(data):
    _save_store(HIGHLIGHTS_FILE, data)


@app.route("/api/highlights", methods=["GET"])
def list_highlights():
    book = request.args.get("book")
    page = request.args.get("page")
    data = _load_highlights()
    out = data["highlights"]
    if book:
        out = [h for h in out if h.get("book") == book]
    if page:
        out = [h for h in out if h.get("page") == page]
    out = sorted(out, key=lambda h: h.get("created_at", ""))
    return jsonify({"highlights": out})


@app.route("/api/highlights", methods=["POST"])
def add_highlight():
    body = request.get_json(silent=True) or {}
    book = (body.get("book") or "").strip()
    page = (body.get("page") or "").strip()
    cid = (body.get("cid") or "").strip()
    text = (body.get("text") or "").strip()
    start = body.get("start")
    end = body.get("end")
    color = (body.get("color") or "yellow").strip()
    if not book or not page or not cid or not text:
        return jsonify({"error": "book, page, cid, and text are required"}), 400
    if not isinstance(start, int) or not isinstance(end, int) or end <= start:
        return jsonify({"error": "start/end (ints, end > start) are required"}), 400
    record = {
        "id": "h_" + uuid.uuid4().hex[:12],
        "book": book,
        "page": page,
        "cid": cid,
        "start": start,
        "end": end,
        "text": text[:1000],
        "color": color,
        "created_at": _now_iso(),
    }
    data = _load_highlights()
    data["highlights"].append(record)
    _save_highlights(data)
    return jsonify({"highlight": record}), 201


@app.route("/api/highlights/<hid>", methods=["DELETE"])
def delete_highlight(hid):
    data = _load_highlights()
    before = len(data["highlights"])
    data["highlights"] = [h for h in data["highlights"] if h.get("id") != hid]
    if len(data["highlights"]) == before:
        return jsonify({"error": "not found"}), 404
    _save_highlights(data)
    # Cascade: remove any notes attached to this highlight
    notes = _load_store(NOTES_FILE, "notes")
    notes["notes"] = [n for n in notes["notes"] if n.get("hid") != hid]
    _save_store(NOTES_FILE, notes)
    return jsonify({"ok": True})


# ---------- notes API ----------
@app.route("/api/notes", methods=["GET"])
def list_notes():
    book = request.args.get("book")
    page = request.args.get("page")
    data = _load_store(NOTES_FILE, "notes")
    out = data["notes"]
    if book:
        out = [n for n in out if n.get("book") == book]
    if page:
        out = [n for n in out if n.get("page") == page]
    out = sorted(out, key=lambda n: n.get("created_at", ""))
    return jsonify({"notes": out})


@app.route("/api/notes", methods=["POST"])
def add_note():
    body = request.get_json(silent=True) or {}
    book = (body.get("book") or "").strip()
    page = (body.get("page") or "").strip()
    cid = (body.get("cid") or "").strip()
    hid = (body.get("hid") or "").strip()
    text = (body.get("text") or "").strip()
    if not book or not page or not cid or not hid or not text:
        return jsonify({"error": "book, page, cid, hid, and text are required"}), 400
    record = {
        "id": "n_" + uuid.uuid4().hex[:12],
        "book": book,
        "page": page,
        "cid": cid,
        "hid": hid,
        "text": text,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    data = _load_store(NOTES_FILE, "notes")
    data["notes"].append(record)
    _save_store(NOTES_FILE, data)
    return jsonify({"note": record}), 201


@app.route("/api/notes/<nid>", methods=["PATCH"])
def update_note(nid):
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    data = _load_store(NOTES_FILE, "notes")
    for n in data["notes"]:
        if n.get("id") == nid:
            n["text"] = text
            n["updated_at"] = _now_iso()
            _save_store(NOTES_FILE, data)
            return jsonify({"note": n})
    return jsonify({"error": "not found"}), 404


@app.route("/api/notes/<nid>", methods=["DELETE"])
def delete_note(nid):
    data = _load_store(NOTES_FILE, "notes")
    before = len(data["notes"])
    data["notes"] = [n for n in data["notes"] if n.get("id") != nid]
    if len(data["notes"]) == before:
        return jsonify({"error": "not found"}), 404
    _save_store(NOTES_FILE, data)
    return jsonify({"ok": True})


# ---------- static website ----------
@app.route("/")
def root_index():
    return send_from_directory(ROOT, "index.html")


@app.route("/<path:path>")
def static_files(path):
    target = ROOT / path
    if target.is_dir():
        idx = target / "index.html"
        if idx.exists():
            return send_from_directory(target, "index.html")
        abort(404)
    if not target.exists():
        abort(404)
    return send_from_directory(target.parent, target.name)


# ---------- startup banner ----------
def _local_ip():
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None


def banner():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    local_url = f"http://localhost:{PORT}/"
    bar = "=" * 64
    print()
    print(bar)
    print("  Slow Books - companion reading guides")
    print(bar)
    tts = tts_service.get_status()
    tts_label = {
        "disabled": "disabled (CPU-only hardware)",
        "initializing": "initializing…",
        "ready": f"ready on {tts['device']}",
        "error": f"error — {tts['message']}",
    }.get(tts["state"], tts["state"])
    print(f"  Local:         {local_url}")
    ip = _local_ip()
    if ip:
        print(f"  Network:       http://{ip}:{PORT}/")
    print(f"  Comments file: {COMMENTS_FILE}")
    print(f"  TTS:           {tts_label}")
    books_dir = ROOT / "books"
    if books_dir.exists():
        for d in sorted(books_dir.iterdir()):
            if d.is_dir() and (d / "index.html").exists():
                print(f"  [book]  {d.name}: {local_url}books/{d.name}/")
    papers_dir = ROOT / "papers"
    if papers_dir.exists():
        for d in sorted(papers_dir.iterdir()):
            if d.is_dir() and (d / "index.html").exists():
                print(f"  [paper] {d.name}: {local_url}papers/{d.name}/")
    print(bar)
    print("  Ctrl-C to stop.")
    print()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    tts_service.init(TTS_DIR)
    banner()
    if "--no-open" not in sys.argv:
        try:
            webbrowser.open(f"http://localhost:{PORT}/")
        except Exception:
            pass
    app.run(host="0.0.0.0", port=PORT, debug=False)
