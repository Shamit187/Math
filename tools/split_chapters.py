"""Extract outline and split Keener's Theoretical Statistics PDF by chapter."""
import os
import re
import sys
import json
from pypdf import PdfReader, PdfWriter

# Force UTF-8 output on Windows console
sys.stdout.reconfigure(encoding="utf-8")

SRC = r"C:\CodeFile\Math\basic_stat\Theoretical Statistics_ Topics for a Core Course (Springer -- Robert W_ Keener (auth_) -- Springer Texts in Statistics, Springer Texts in Statistics, -- isbn13 9780387938387 -- 974457952054774bade7ba447d7a65e8 -- A.pdf"
OUT_DIR = r"C:\CodeFile\Math\basic_stat\chapters"
os.makedirs(OUT_DIR, exist_ok=True)

reader = PdfReader(SRC)
total = len(reader.pages)


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


entries = walk(reader.outline)

# Top-level chapter entries -- depth 0, title starts with digit followed by space
chapter_pattern = re.compile(r"^(\d+)\s+(.+)$")
chapters = []
for d, t, p in entries:
    if d == 0 and chapter_pattern.match(t) and p is not None:
        m = chapter_pattern.match(t)
        chapters.append({"num": int(m.group(1)), "title": m.group(2).strip(), "start": p})

# Also capture key front/back matter top-level items
front_back = []
for d, t, p in entries:
    if d == 0 and not chapter_pattern.match(t) and p is not None:
        front_back.append({"title": t.strip(), "start": p})

# Determine end pages for each chapter (exclusive) -- next chapter's start, or last back-matter section
all_starts = [c["start"] for c in chapters]
# Find the start of back matter after the last chapter
last_chap_start = chapters[-1]["start"] if chapters else 0
back_after = [fb for fb in front_back if fb["start"] > last_chap_start]
back_after_first = back_after[0]["start"] if back_after else total

for i, c in enumerate(chapters):
    next_start = chapters[i + 1]["start"] if i + 1 < len(chapters) else back_after_first
    c["end"] = next_start  # exclusive

print(f"Total pages: {total}")
print(f"Found {len(chapters)} chapters\n")
for c in chapters:
    print(f"  Ch {c['num']:2d}: pages {c['start']+1}-{c['end']} ({c['end']-c['start']} pages) -- {c['title']}")

print("\nFront/back matter top-level items:")
for fb in front_back:
    print(f"  page {fb['start']+1}: {fb['title']}")

# Save metadata
meta_path = os.path.join(OUT_DIR, "chapters.json")
with open(meta_path, "w", encoding="utf-8") as f:
    json.dump({"chapters": chapters, "front_back": front_back, "total_pages": total}, f, indent=2, ensure_ascii=False)
print(f"\nMetadata written to {meta_path}")


def safe_name(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s[:80]


# Split chapters
for c in chapters:
    writer = PdfWriter()
    for p in range(c["start"], c["end"]):
        writer.add_page(reader.pages[p])
    fname = f"ch{c['num']:02d}_{safe_name(c['title'])}.pdf"
    fpath = os.path.join(OUT_DIR, fname)
    with open(fpath, "wb") as f:
        writer.write(f)
    print(f"  wrote {fname} ({c['end']-c['start']} pages)")

# Also split front matter as a single bundle (pages 0 .. first chapter start)
if chapters:
    fm_writer = PdfWriter()
    for p in range(0, chapters[0]["start"]):
        fm_writer.add_page(reader.pages[p])
    fm_path = os.path.join(OUT_DIR, "ch00_front_matter.pdf")
    with open(fm_path, "wb") as f:
        fm_writer.write(f)
    print(f"  wrote ch00_front_matter.pdf ({chapters[0]['start']} pages)")

# Back matter bundle
if back_after_first < total:
    bm_writer = PdfWriter()
    for p in range(back_after_first, total):
        bm_writer.add_page(reader.pages[p])
    bm_path = os.path.join(OUT_DIR, "ch99_back_matter.pdf")
    with open(bm_path, "wb") as f:
        bm_writer.write(f)
    print(f"  wrote ch99_back_matter.pdf ({total - back_after_first} pages)")

print("\nDone.")
