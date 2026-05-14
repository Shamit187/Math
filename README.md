# Slow Books

Companion reading guides for math and statistics textbooks. Each book gets its own
chapter-by-chapter walkthrough with intuition boxes, worked examples, and a comment
system you can use to flag anything that didn't make sense.

## Run it

```powershell
python serve.py
```

Browser auto-opens at <http://localhost:8765/>. One process, one port, the whole
site — root index, every book's home, every chapter page, every asset, and the
comments API.

## Layout

```
C:\CodeFile\Math\
├── serve.py                  # the only server
├── index.html                # root book list
├── css/                      # shared assets
├── js/
├── books/
│   └── basic_stat/           # one folder per book
│       ├── index.html        # this book's home (chapter list)
│       ├── source.pdf
│       ├── chapter-pdfs/     # split per-chapter PDFs (for tooling)
│       ├── chapter-texts/    # extracted text (for the writer agents)
│       └── chapters/         # served HTML
│           ├── ch01.html
│           └── ...
├── comments/
│   └── comments.json         # all books' comments, keyed by (book, page, cid)
└── tools/
    ├── add_cids.py           # idempotent CID tagger
    ├── extract_text.py       # one-PDF text extractor
    ├── extract_all.py        # batch text extractor for a book
    ├── generate_stubs.py
    └── split_chapters.py
```

## Adding a new book

1. Create `books/<slug>/` and drop `source.pdf` in it.
2. Use `tools/split_chapters.py` (adapt the source path) to write per-chapter PDFs into `books/<slug>/chapter-pdfs/` and a `chapters.json` outline.
3. Run `tools/extract_all.py` (adapt the source path) to extract `chapter-texts/chNN_text.txt`.
4. Write `books/<slug>/index.html` (use `books/basic_stat/index.html` as a template — keep the absolute `/css/...` and `/js/...` paths, set `data-book="<slug>"`, link the chapters).
5. Write each `books/<slug>/chapters/chNN.html`. Easiest: spawn one writer agent per chapter using the prompt template that built basic_stat.
6. Run `python tools/add_cids.py` to add stable IDs and wire the comments client.
7. Add the new book to the root `index.html` chapter list.

## Leaving comments

- Hover any paragraph, list, heading, or callout box in a chapter. A `💬` button appears in the right gutter.
- Click it (or press **C** while hovering) to open a comment panel.
- Type what didn't make sense. Save.
- Comments persist to `comments/comments.json` with `{book, page, cid, text, block_excerpt, created_at}`.

The header badge reads `● comments synced` when the server is reachable; `○ comments local-only` if you opened the HTML files directly via `file://`.

## Reviewing comments

Ask: *"review my comments on basic_stat"* — Claude reads `comments/comments.json`,
looks up each comment's `(book, page, cid)` in the HTML to find the affected block,
and rewrites the prose for clarity. Existing comments stay attached to their CIDs
through edits.

## API

The server exposes:

| Endpoint | Purpose |
|---|---|
| `GET  /api/health`  | Reachability ping |
| `GET  /api/books`   | List discovered books on disk |
| `GET  /api/comments?book=<>&page=<>` | List comments, optionally filtered |
| `POST /api/comments` | `{book, page, cid, text, block_excerpt}` → adds a comment |
| `PATCH /api/comments/<id>` | `{text}` → edits an existing comment |
| `DELETE /api/comments/<id>` | Removes a comment |
