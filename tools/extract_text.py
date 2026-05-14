"""Extract text from a chapter PDF for source material."""
import sys
from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")

path = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else None

reader = PdfReader(path)
chunks = []
for i, page in enumerate(reader.pages):
    chunks.append(f"\n===== PAGE {i+1} =====\n")
    chunks.append(page.extract_text() or "")

text = "\n".join(chunks)
if out:
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {out} ({len(text)} chars)")
else:
    print(text)
