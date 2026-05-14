"""
Walk every book's HTML pages and assign stable data-cid attributes to each
commentable content block. Idempotent: existing IDs are preserved.

Layout (multi-book):
    ROOT/index.html                          -> skipped (no comments at root)
    ROOT/books/<book>/index.html             -> book=<book>, page="index"
    ROOT/books/<book>/chapters/chNN.html     -> book=<book>, page="chNN"

This script:
  - Adds data-cid to h2, h3, p, ul, ol, figure, div.box
  - Adds data-book="<book>" and data-page="<key>" to <body>
  - Links /css/comments.css and /js/comments.js into <head>/<body>

Pagekey + cid are scoped per-book, so two books can both have a page named
"index" or "ch01" without colliding — the comments API stores (book, page, cid).
"""
import re
import sys
from pathlib import Path
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent

CONTAINER_TAGS = {"h2", "h3", "p", "ul", "ol", "figure"}


def is_commentable(tag):
    if tag.name in CONTAINER_TAGS:
        return True
    if tag.name == "div" and "box" in (tag.get("class") or []):
        return True
    return False


def page_targets():
    """Yield (path, book, pagekey) for every HTML page to tag."""
    books = ROOT / "books"
    if not books.exists():
        return
    for book_dir in sorted(books.iterdir()):
        if not book_dir.is_dir():
            continue
        book = book_dir.name
        idx = book_dir / "index.html"
        if idx.exists():
            yield (idx, book, "index")
        chap_dir = book_dir / "chapters"
        if chap_dir.exists():
            for p in sorted(chap_dir.glob("ch*.html")):
                yield (p, book, p.stem)  # "ch01", "ch02", ...


def assign_ids(soup, pagekey):
    article = soup.find("article", class_="content")
    target = article if article else soup.body
    if target is None:
        return False

    existing = set()
    pattern = re.compile(rf"^{re.escape(pagekey)}-(\d{{3,}})$")
    highest = 0
    for tag in target.find_all(attrs={"data-cid": True}):
        cid = tag["data-cid"]
        existing.add(cid)
        m = pattern.match(cid)
        if m:
            highest = max(highest, int(m.group(1)))
    counter = ((highest // 10) + 1) * 10

    changed = False
    for tag in target.find_all(is_commentable):
        if tag.has_attr("data-cid"):
            continue
        if not tag.get_text(strip=True) and tag.name != "figure":
            continue
        new_id = f"{pagekey}-{counter:03d}"
        while new_id in existing:
            counter += 10
            new_id = f"{pagekey}-{counter:03d}"
        tag["data-cid"] = new_id
        existing.add(new_id)
        counter += 10
        changed = True
    return changed


def ensure_assets(soup, book, pagekey):
    head = soup.head
    body = soup.body
    if head is None or body is None:
        return False
    changed = False

    css_href = "/css/comments.css"
    if not head.find("link", href=css_href):
        style_link = head.find("link", href=re.compile(r"/?css/style\.css$"))
        new_link = soup.new_tag("link", rel="stylesheet", href=css_href)
        if style_link:
            style_link.insert_after(new_link)
        else:
            head.append(new_link)
        changed = True

    js_src = "/js/comments.js"
    if not body.find("script", src=js_src):
        main_script = body.find("script", src=re.compile(r"/?js/main\.js$"))
        new_script = soup.new_tag("script", src=js_src)
        if main_script:
            main_script.insert_after(new_script)
        else:
            body.append(new_script)
        changed = True

    if body.get("data-book") != book:
        body["data-book"] = book
        changed = True
    if body.get("data-page") != pagekey:
        body["data-page"] = pagekey
        changed = True
    return changed


def process(path: Path, book: str, pagekey: str):
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")
    a = assign_ids(soup, pagekey)
    b = ensure_assets(soup, book, pagekey)
    if a or b:
        path.write_text(str(soup), encoding="utf-8")
        print(f"  updated {path.relative_to(ROOT)} (ids+={'y' if a else 'n'}, assets+={'y' if b else 'n'})")
    else:
        print(f"  no change {path.relative_to(ROOT)}")


def main():
    for path, book, key in page_targets():
        process(path, book, key)
    print("done")


if __name__ == "__main__":
    main()
