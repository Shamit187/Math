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

from flask import Flask, jsonify, request, send_from_directory, abort
from flask_cors import CORS

ROOT = Path(__file__).resolve().parent
COMMENTS_DIR = ROOT / "comments"
COMMENTS_FILE = COMMENTS_DIR / "comments.json"
COMMENTS_DIR.mkdir(parents=True, exist_ok=True)

PORT = 8765

app = Flask(__name__, static_folder=None)
CORS(app)


# ---------- comment storage ----------
def _load():
    if not COMMENTS_FILE.exists():
        return {"comments": []}
    try:
        with COMMENTS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("comments", [])
            return data
    except Exception:
        return {"comments": []}


def _save(data):
    tmp = COMMENTS_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(COMMENTS_FILE)


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------- API ----------
@app.route("/api/health")
def health():
    return jsonify({"ok": True, "comments_file": str(COMMENTS_FILE)})


@app.route("/api/books")
def list_books():
    books_dir = ROOT / "books"
    out = []
    if books_dir.exists():
        for d in sorted(books_dir.iterdir()):
            if not d.is_dir():
                continue
            chapters = sorted((d / "chapters").glob("ch*.html")) if (d / "chapters").exists() else []
            out.append({
                "slug": d.name,
                "url": f"/books/{d.name}/",
                "n_chapters": len(chapters),
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
def banner():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    url = f"http://localhost:{PORT}/"
    bar = "=" * 64
    print()
    print(bar)
    print("  Slow Books - companion reading guides")
    print(bar)
    print(f"  Root:          {url}")
    print(f"  Books API:     {url}api/books")
    print(f"  Comments API:  {url}api/comments")
    print(f"  Comments file: {COMMENTS_FILE}")
    # Discover books and print them
    books_dir = ROOT / "books"
    if books_dir.exists():
        for d in sorted(books_dir.iterdir()):
            if d.is_dir() and (d / "index.html").exists():
                print(f"  - {d.name}: {url}books/{d.name}/")
    print(bar)
    print("  Ctrl-C to stop.")
    print()


if __name__ == "__main__":
    banner()
    if "--no-open" not in sys.argv:
        try:
            webbrowser.open(f"http://localhost:{PORT}/")
        except Exception:
            pass
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app.run(host="127.0.0.1", port=PORT, debug=False)
