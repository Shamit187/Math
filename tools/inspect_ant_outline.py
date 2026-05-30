"""Inspect the outline of the Neukirch Algebraic Number Theory PDF."""
import sys
from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")

SRC = sys.argv[1]
reader = PdfReader(SRC)
print(f"Total pages: {len(reader.pages)}")


def walk(outline, depth=0, acc=None):
    if acc is None:
        acc = []
    for item in outline:
        if isinstance(item, list):
            walk(item, depth + 1, acc)
        else:
            try:
                page_index = reader.get_destination_page_number(item)
            except Exception:
                page_index = None
            acc.append((depth, item.title, page_index))
    return acc


try:
    entries = walk(reader.outline)
    print(f"Outline entries: {len(entries)}\n")
    for d, t, p in entries:
        page = (p + 1) if p is not None else "?"
        print(f"{'  ' * d}[p{page}] {t}")
except Exception as e:
    print(f"No usable outline: {e}")
