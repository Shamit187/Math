"""Extract text from every chapter PDF (ch02..ch20) for use by writer agents."""
import os
import sys
from pathlib import Path
from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")

CH_DIR = Path(r"C:\CodeFile\Math\basic_stat\chapters")

for pdf in sorted(CH_DIR.glob("ch[0-9][0-9]_*.pdf")):
    out = pdf.with_name(pdf.stem.split("_", 1)[0] + "_text.txt")
    if out.exists() and out.stat().st_size > 1000:
        print(f"skip {pdf.name} (text already extracted)")
        continue
    reader = PdfReader(str(pdf))
    chunks = []
    for i, page in enumerate(reader.pages):
        chunks.append(f"\n===== PAGE {i+1} =====\n")
        chunks.append(page.extract_text() or "")
    text = "\n".join(chunks)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {out.name} ({len(text)} chars from {len(reader.pages)} pages)")

print("done")
