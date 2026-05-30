"""Split Neukirch's Algebraic Number Theory PDF by chapter and extract text.

Builds chapters.json (with section lists), per-chapter PDFs under chapter-pdfs/,
and per-chapter text under chapter-texts/.
"""
import os
import re
import sys
import json
from pypdf import PdfReader, PdfWriter

sys.stdout.reconfigure(encoding="utf-8")

SRC = r"C:\CodeFile\Math\books\Algebraic Number Theory -- Jürgen Neukirch, Norbert Schappacher -- 1, 20130314 -- Springer Science & Business Media -- isbn13 9783662039830 -- 1b8f00dc6414ba6344a8b7726f6e9366 -- Anna’s Archive.pdf"
BOOK_DIR = r"C:\CodeFile\Math\books\algebraic_number_theory"
PDF_DIR = os.path.join(BOOK_DIR, "chapter-pdfs")
TXT_DIR = os.path.join(BOOK_DIR, "chapter-texts")
os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(TXT_DIR, exist_ok=True)

reader = PdfReader(SRC)
total = len(reader.pages)

# Roman numeral -> arabic
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
         "VIII": 8, "IX": 9, "X": 10}


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

chap_re = re.compile(r"^Chapter\s+([IVX]+)\.\s+(.+)$")
sec_re = re.compile(r"^(\d+)\.\s+(.+)$")

chapters = []
current = None
for d, t, p in entries:
    t = t.strip()
    mc = chap_re.match(t)
    if mc and p is not None:
        num = ROMAN[mc.group(1)]
        current = {"num": num, "roman": mc.group(1), "title": mc.group(2).strip(),
                   "start": p, "sections": []}
        chapters.append(current)
        continue
    # Section directly under a chapter
    ms = sec_re.match(t)
    if ms and current is not None and p is not None and d >= 1:
        current["sections"].append({"num": int(ms.group(1)),
                                     "title": ms.group(2).strip(),
                                     "start": p})

# Back matter start (first top-level non-chapter entry after last chapter)
last_start = chapters[-1]["start"]
back_start = total
for d, t, p in entries:
    if d == 0 and p is not None and p > last_start and not chap_re.match(t.strip()):
        back_start = p
        break

for i, c in enumerate(chapters):
    c["end"] = chapters[i + 1]["start"] if i + 1 < len(chapters) else back_start

print(f"Total pages: {total}")
print(f"Found {len(chapters)} chapters\n")
for c in chapters:
    print(f"  Ch {c['num']} ({c['roman']}): PDF pages {c['start']+1}-{c['end']} "
          f"({c['end']-c['start']} pp, {len(c['sections'])} sections) -- {c['title']}")

# Save metadata
meta_path = os.path.join(BOOK_DIR, "chapters.json")
with open(meta_path, "w", encoding="utf-8") as f:
    json.dump({"chapters": chapters, "total_pages": total,
               "back_start": back_start}, f, indent=2, ensure_ascii=False)
print(f"\nMetadata -> {meta_path}")

# Split + extract per chapter
for c in chapters:
    writer = PdfWriter()
    for p in range(c["start"], c["end"]):
        writer.add_page(reader.pages[p])
    pdf_path = os.path.join(PDF_DIR, f"ch{c['num']:02d}.pdf")
    with open(pdf_path, "wb") as f:
        writer.write(f)

    # Extract text
    chunks = []
    for p in range(c["start"], c["end"]):
        chunks.append(f"\n===== PDF PAGE {p+1} =====\n")
        chunks.append(reader.pages[p].extract_text() or "")
    text = "\n".join(chunks)
    txt_path = os.path.join(TXT_DIR, f"ch{c['num']:02d}_text.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  ch{c['num']:02d}: wrote PDF ({c['end']-c['start']} pp) + text ({len(text)} chars)")

print("\nDone.")
