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
  /api/books                 -> flat list of books/papers detected on disk
  /api/catalog               -> faceted search (q, type, tag, topic, sort, page)
  /api/comments              -> GET (filter by book and/or page), POST
  /api/comments/<id>         -> DELETE, PATCH
  /api/address-comments      -> POST (localhost only): open a PowerShell window
                                running Claude Code to revise the page from its
                                reader comments
"""
import json
import logging
import re
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from collections import Counter
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, abort, Response
from flask_cors import CORS

import tts_service

ROOT = Path(__file__).resolve().parent
COMMENTS_DIR = ROOT / "comments"
COMMENTS_FILE = COMMENTS_DIR / "comments.json"
HIGHLIGHTS_FILE = COMMENTS_DIR / "highlights.json"
NOTES_FILE = COMMENTS_DIR / "notes.json"
READING_FILE = COMMENTS_DIR / "reading.json"
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


# ---------- catalog: a cached, faceted index of every book and paper ----------
# Built once from each item's meta.json and rebuilt only when a meta.json (or the
# set of content dirs) changes, so it stays fast at thousands of items. Every
# query is filtered/sorted/paginated server-side and returns facet counts, which
# is what keeps the homepage navigable as the library saturates.
_catalog_lock = threading.Lock()
_catalog_cache = {"sig": None, "items": None, "checked": 0.0}
_CATALOG_TTL = 2.0  # seconds between change-checks (avoids re-stat'ing every request)


def _topic_paths(meta) -> list:
    """meta['topics'] is one or more 'Field/Subfield/Subject' strings; return a
    list of cleaned segment-lists."""
    raw = meta.get("topics") or []
    if isinstance(raw, str):
        raw = [raw]
    out = []
    for p in raw:
        parts = [seg.strip() for seg in str(p).split("/") if seg.strip()]
        if parts:
            out.append(parts)
    return out


def _join_authors(authors) -> str:
    """Normalize an authors field (str or list) to a single display string."""
    if isinstance(authors, (list, tuple)):
        return ", ".join(str(a).strip() for a in authors if str(a).strip())
    return str(authors)


def _item_from_dir(d: Path, kind: str) -> dict:
    meta = _read_meta(d)
    year = meta.get("year")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None
    item = {
        "slug": d.name,
        "type": kind,
        "title": meta.get("title", d.name),
        "subtitle": meta.get("subtitle", ""),
        "authors": _join_authors(meta.get("authors", "")),
        "venue": meta.get("venue", ""),
        "year": year,
        "description": meta.get("description", ""),
        "topics": _topic_paths(meta),
        "tags": [str(t).strip() for t in (meta.get("tags") or []) if str(t).strip()],
    }
    if kind == "book":
        chapters = sorted((d / "chapters").glob("ch*.html")) if (d / "chapters").exists() else []
        item["n_chapters"] = len(chapters)
        item["url"] = f"/books/{d.name}/"
    else:
        item["url"] = f"/papers/{d.name}/"
    return item


def _content_dirs():
    for base, kind in ((ROOT / "books", "book"), (ROOT / "papers", "paper")):
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            if kind == "paper" and not (d / "index.html").exists():
                continue
            yield d, kind


def _catalog_signature() -> tuple:
    sig = []
    for d, kind in _content_dirs():
        mf = d / "meta.json"
        sig.append((str(d), kind, mf.stat().st_mtime_ns if mf.exists() else 0))
    return tuple(sig)


def get_catalog() -> list:
    """Return the cached catalog, rebuilding only when content/meta changes.
    The change-check itself is throttled to once per _CATALOG_TTL so a busy
    homepage doesn't re-stat thousands of meta.json files on every request."""
    now = time.monotonic()
    with _catalog_lock:
        if _catalog_cache["items"] is not None and (now - _catalog_cache["checked"]) < _CATALOG_TTL:
            return _catalog_cache["items"]
        _catalog_cache["checked"] = now
        sig = _catalog_signature()
        if _catalog_cache["sig"] != sig:
            items = []
            for d, kind in _content_dirs():
                it = _item_from_dir(d, kind)
                it["_hay"] = " ".join([
                    it["title"], it["subtitle"], it["authors"], it["venue"],
                    it["description"], " ".join(it["tags"]),
                    " ".join("/".join(p) for p in it["topics"]),
                ]).lower()
                it["_tagset"] = {t.lower() for t in it["tags"]}
                items.append(it)
            _catalog_cache["items"] = items
            _catalog_cache["sig"] = sig
        return _catalog_cache["items"]


def _public_item(it: dict) -> dict:
    return {k: v for k, v in it.items() if not k.startswith("_")}


def _topic_prefix_match(it: dict, prefix: list) -> bool:
    if not prefix:
        return True
    low = [p.lower() for p in prefix]
    for path in it["topics"]:
        if len(path) >= len(low) and [s.lower() for s in path[:len(low)]] == low:
            return True
    return False


def _build_topic_tree(items: list) -> list:
    """Nested topic tree with a distinct-item count at every node."""
    roots = {}
    for it in items:
        for path in it["topics"]:
            cur, acc = roots, []
            for part in path:
                acc = acc + [part]
                node = cur.get(part)
                if node is None:
                    node = {"name": part, "path": "/".join(acc), "slugs": set(), "children": {}}
                    cur[part] = node
                node["slugs"].add(it["slug"])
                cur = node["children"]

    def to_list(children):
        out = []
        for name in sorted(children):
            n = children[name]
            out.append({
                "name": n["name"],
                "path": n["path"],
                "count": len(n["slugs"]),
                "children": to_list(n["children"]),
            })
        return out

    return to_list(roots)


def _tag_facets(items: list, limit: int = 60) -> list:
    c = Counter()
    for it in items:
        for t in dict.fromkeys(it["tags"]):  # dedup within an item, keep case
            c[t] += 1
    return [{"name": t, "count": n} for t, n in c.most_common(limit)]


@app.route("/api/books")
def list_books():
    # Back-compat: the flat list, now enriched with topics/tags/year.
    return jsonify({"books": [_public_item(it) for it in get_catalog()]})


@app.route("/api/catalog")
def api_catalog():
    """Faceted search over the whole library.

    Query params: q, type (book|paper), tag (repeatable, AND), topic (a
    Field/Subfield path prefix), sort (relevance|title|year_desc|year_asc),
    offset, limit. Returns the page of items plus facet counts (each facet is
    computed ignoring its own dimension, so selections narrow the others)."""
    items = get_catalog()
    reading = _reading_map()

    def is_read(it):
        return reading.get(it["slug"], False)

    q = (request.args.get("q") or "").strip().lower()
    tokens = [t for t in re.split(r"\s+", q) if t]
    typ = (request.args.get("type") or "").strip().lower()
    if typ not in ("book", "paper"):
        typ = ""
    read_filter = (request.args.get("read") or "").strip().lower()
    if read_filter not in ("read", "unread"):
        read_filter = ""
    topic_parts = [s.strip() for s in (request.args.get("topic") or "").split("/") if s.strip()]
    tags = [t.strip().lower() for t in request.args.getlist("tag") if t.strip()]
    sort = (request.args.get("sort") or "relevance").strip()
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(request.args.get("limit", 24))
    except (TypeError, ValueError):
        limit = 24
    limit = max(1, min(limit, 200))

    def passes(it, ignore=()):
        if "type" not in ignore and typ and it["type"] != typ:
            return False
        if "read" not in ignore and read_filter and \
                ((read_filter == "read") != is_read(it)):
            return False
        if "topic" not in ignore and topic_parts and not _topic_prefix_match(it, topic_parts):
            return False
        if "tag" not in ignore and tags and not all(tg in it["_tagset"] for tg in tags):
            return False
        if "q" not in ignore and tokens and not all(tok in it["_hay"] for tok in tokens):
            return False
        return True

    def score(it):
        s = 0
        title = it["title"].lower()
        tagblob = " ".join(it["tags"]).lower()
        for tok in tokens:
            if tok in title:
                s += 5
            if tok in tagblob:
                s += 3
            s += 1
        return s

    filtered = [it for it in items if passes(it)]
    if sort == "title":
        filtered.sort(key=lambda it: it["title"].lower())
    elif sort == "year_desc":
        filtered.sort(key=lambda it: (-(it["year"] if it["year"] is not None else -99999), it["title"].lower()))
    elif sort == "year_asc":
        filtered.sort(key=lambda it: (it["year"] if it["year"] is not None else 99999, it["title"].lower()))
    elif tokens:  # relevance (default) with an active query
        filtered.sort(key=lambda it: (-score(it), it["title"].lower()))
    else:
        filtered.sort(key=lambda it: it["title"].lower())

    total = len(filtered)
    page = []
    for it in filtered[offset:offset + limit]:
        pub = _public_item(it)
        pub["read"] = is_read(it)
        page.append(pub)

    topic_items = [it for it in items if passes(it, ignore=("topic",))]
    tag_items = [it for it in items if passes(it, ignore=("tag",))]
    type_items = [it for it in items if passes(it, ignore=("type",))]
    read_items = [it for it in items if passes(it, ignore=("read",))]
    facets = {
        "topics": _build_topic_tree(topic_items),
        "tags": _tag_facets(tag_items),
        "types": {
            "all": len(type_items),
            "book": sum(1 for it in type_items if it["type"] == "book"),
            "paper": sum(1 for it in type_items if it["type"] == "paper"),
        },
        "reading": {
            "all": len(read_items),
            "read": sum(1 for it in read_items if is_read(it)),
            "unread": sum(1 for it in read_items if not is_read(it)),
        },
    }
    return jsonify({"total": total, "offset": offset, "limit": limit, "items": page, "facets": facets})

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


# ---------- "address comments" — hand a page's comments to Claude Code ----------
_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _ps_single_quote(s: str) -> str:
    """Quote a string for use inside a PowerShell single-quoted literal."""
    return "'" + s.replace("'", "''") + "'"


@app.route("/api/address-comments", methods=["POST"])
def address_comments():
    """Open a PowerShell window on the desktop and run Claude Code to revise the
    page that the comments refer to.

    This launches `claude --dangerously-skip-permissions`, i.e. it runs an agent
    that can edit files with no prompts — so it is restricted to requests coming
    from the local machine, and the command is built entirely server-side from a
    validated book/page (no raw browser text reaches the shell)."""
    remote = request.remote_addr or ""
    if remote not in ("127.0.0.1", "::1", "localhost"):
        return jsonify({"error": "address-comments is only available on localhost"}), 403
    if not sys.platform.startswith("win"):
        return jsonify({"error": "address-comments currently supports Windows/PowerShell only"}), 400

    body = request.get_json(silent=True) or {}
    book = (body.get("book") or "").strip()
    page = (body.get("page") or "").strip()
    if not _SLUG_RE.match(book) or not _SLUG_RE.match(page):
        return jsonify({"error": "invalid book or page"}), 400

    # Resolve the actual page file the comments point at. A chapter page (chNN)
    # must map to its own chapter file; only the book/paper home pages fall back
    # to index.html, so a bogus page slug 404s instead of silently retargeting.
    candidates = [ROOT / "books" / book / "chapters" / f"{page}.html"]
    if page == "index":
        candidates.append(ROOT / "books" / book / "index.html")
    if page == "main":
        candidates.append(ROOT / "papers" / book / "index.html")
        candidates.append(ROOT / "books" / book / "index.html")
    target = next((c for c in candidates if c.exists()), None)
    if target is None:
        return jsonify({"error": f"no page file found for book={book}, page={page}"}), 404
    rel = target.relative_to(ROOT).as_posix()

    pending = [c for c in _load()["comments"]
               if c.get("book") == book and c.get("page") == page]

    # NOTE: keep this prompt free of double-quote characters. It is passed through
    # subprocess -> powershell.exe -Command inside a single-quoted PowerShell string;
    # embedded double quotes survive Windows command-line quoting poorly, whereas a
    # quote-free instruction transports cleanly. (Apostrophes are fine — they are
    # doubled by _ps_single_quote.)
    prompt = (
        "You are working in the Slow Books project (your current directory is the project root). "
        "A reader has left comments that need to be addressed. "
        f"Read comments/comments.json and find every comment whose book field equals {book} and whose "
        f"page field equals {page}. "
        f"Those comments are about the chapter file {rel}; each comment's cid field is the data-cid of the exact "
        "block it refers to, and its text field is the reader's question or confusion. "
        "For each such comment, revise that page to resolve the confusion: clarify the prose, and/or add a "
        "box intuition (or a box comment-response whose data-resolves attribute is set to the comment id) "
        "immediately after the referenced block. "
        "Follow CLAUDE.md exactly: wrap every math expression in a tts-math span with a plain-English data-tts "
        "reading, give any new block a data-cid that preserves the increasing order, and escape the angle-bracket "
        "and ampersand characters inside math. "
        "Do not delete or rewrite unrelated content. Once a comment is fully addressed, remove that entry from "
        "comments/comments.json so it is not handled again. Finish with a short summary of what you changed."
    )

    # Launch Claude INTERACTIVELY (not headless -p). Headless/print mode is
    # non-interactive, so it cannot complete Claude's subscription sign-in — the
    # Pro/Max OAuth login and the first-run --dangerously-skip-permissions trust
    # prompt both need a real TTY — which is why a -p terminal could never "sort
    # out the subscription". An interactive session authenticates normally and
    # starts pre-loaded on the prompt below.
    #
    # We still launch PowerShell WITHOUT -NoExit, so the console closes once the
    # Claude session ends (type /exit when the comments are addressed): on a clean
    # exit it shows a confirmation and closes; on a non-zero exit it stays open so
    # the error remains visible.
    ps_lines = [
        f"Set-Location -LiteralPath {_ps_single_quote(str(ROOT))}",
        f"Write-Host {_ps_single_quote('Addressing reader comments on ' + rel + '. Type /exit when done to close this window.')} -ForegroundColor Cyan",
        f"claude --dangerously-skip-permissions {_ps_single_quote(prompt)}",
        "if ($LASTEXITCODE -eq 0) { Write-Host 'Claude session ended - closing.' -ForegroundColor Green; "
        "Start-Sleep -Seconds 2 } "
        "else { Write-Host ('Claude exited with code ' + $LASTEXITCODE + '.') -ForegroundColor Red; "
        "Read-Host 'Press Enter to close' }",
    ]
    ps_script = "; ".join(ps_lines)

    CREATE_NEW_CONSOLE = 0x00000010
    try:
        subprocess.Popen(
            ["powershell", "-Command", ps_script],
            creationflags=CREATE_NEW_CONSOLE,
            cwd=str(ROOT),
        )
    except FileNotFoundError:
        return jsonify({"error": "powershell not found on PATH"}), 500
    except Exception as exc:
        logging.getLogger(__name__).error("address-comments launch failed: %s", exc, exc_info=True)
        return jsonify({"error": "failed to launch terminal"}), 500

    return jsonify({"ok": True, "page_file": rel, "pending_comments": len(pending)})


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


# ---------- reading status API ----------
# A flat per-item read/unread flag keyed by the content slug (the <body>'s
# data-book). One record per item; POST upserts. Read by the catalog so the
# homepage can badge and filter read vs. unread items.
def _reading_map() -> dict:
    """slug -> bool (read). Missing slug means unread."""
    data = _load_store(READING_FILE, "reading")
    return {r.get("book"): bool(r.get("read")) for r in data["reading"] if r.get("book")}


@app.route("/api/reading-status", methods=["GET"])
def list_reading():
    book = request.args.get("book")
    data = _load_store(READING_FILE, "reading")
    out = data["reading"]
    if book:
        out = [r for r in out if r.get("book") == book]
    return jsonify({"reading": out})


@app.route("/api/reading-status", methods=["POST"])
def set_reading():
    body = request.get_json(silent=True) or {}
    book = (body.get("book") or "").strip()
    if not book:
        return jsonify({"error": "book required"}), 400
    read = bool(body.get("read"))
    data = _load_store(READING_FILE, "reading")
    rec = next((r for r in data["reading"] if r.get("book") == book), None)
    if rec is None:
        rec = {"book": book, "read": read,
               "created_at": _now_iso(), "updated_at": _now_iso()}
        data["reading"].append(rec)
    else:
        rec["read"] = read
        rec["updated_at"] = _now_iso()
    _save_store(READING_FILE, data)
    return jsonify({"reading": rec})


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
