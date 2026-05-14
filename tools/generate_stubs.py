"""Generate stub HTML pages for chapters 2-20."""
import os
import re
import sys
from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")

CHAPTERS_DIR = r"C:\CodeFile\Math\basic_stat\chapters"
SRC = r"C:\CodeFile\Math\basic_stat\Theoretical Statistics_ Topics for a Core Course (Springer -- Robert W_ Keener (auth_) -- Springer Texts in Statistics, Springer Texts in Statistics, -- isbn13 9780387938387 -- 974457952054774bade7ba447d7a65e8 -- A.pdf"
OUT_DIR = r"C:\CodeFile\Math\basic_stat\website\chapters"

reader = PdfReader(SRC)


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
chapter_pattern = re.compile(r"^(\d+)\s+(.+)$")
section_pattern = re.compile(r"^(\d+)\.(\d+)\s+(.+)$")

# Build chapter -> sections map
chapter_data = {}
current_chapter = None
for d, t, p in entries:
    if d == 0:
        m = chapter_pattern.match(t)
        if m:
            num = int(m.group(1))
            title = m.group(2).strip()
            chapter_data[num] = {"title": title, "sections": [], "start": p}
            current_chapter = num
        else:
            current_chapter = None
    elif d == 1 and current_chapter is not None:
        m = section_pattern.match(t)
        if m:
            ch_num = int(m.group(1))
            sec_num = int(m.group(2))
            sec_title = m.group(3).strip()
            # Strip trailing problem-count digit like "Problems5" -> "Problems"
            sec_title = re.sub(r"(Problems?)\s*\d+$", r"\1", sec_title).strip()
            sec_title = re.sub(r"(.+)\d+$", lambda mm: mm.group(1).rstrip() if not mm.group(1).rstrip().endswith(("of", "for", "and")) else mm.group(0), sec_title)
            # Clean weird unicode dashes
            sec_title = sec_title.replace("–", "-").replace("—", "-")
            if ch_num == current_chapter:
                chapter_data[ch_num]["sections"].append({"num": f"{ch_num}.{sec_num}", "title": sec_title})

# Brief one-line "why this chapter" descriptions
chapter_taglines = {
    1: "Probability and Measure",
    2: "A family of distributions with magical structure — the workhorse of theoretical statistics.",
    3: "What information does a statistic carry? Sufficiency, completeness, and the Rao-Blackwell idea.",
    4: "Estimators that are unbiased — and when 'unbiased' is and isn't a good goal.",
    5: "Exponential families with constraints — the geometry gets richer.",
    6: "Conditional distributions done properly, including the measure-theoretic case.",
    7: "Bayes estimators, posterior expectations, and what they minimize.",
    8: "What happens to estimators as the sample size grows: consistency, convergence in distribution, CLT.",
    9: "Maximum likelihood as a special case of solving estimating equations — and how to prove it works asymptotically.",
    10: "Estimation in problems that have a symmetry — what 'best' means when invariance is required.",
    11: "Borrowing strength across problems: Stein's paradox and shrinkage estimators.",
    12: "Hypothesis testing from scratch: significance, power, uniformly most powerful tests, Neyman-Pearson.",
    13: "Optimal tests when the parameter is a vector — and the difficulties that introduces.",
    14: "Regression done with linear algebra: estimation, Gauss-Markov, projections.",
    15: "Modern Bayesian inference: prior selection, MCMC, model comparison.",
    16: "What is the best possible estimator in large samples? Asymptotic efficiency bounds.",
    17: "Wilks' theorem and the asymptotic chi-squared distribution of likelihood ratios.",
    18: "Estimating functions without parametric assumptions: kernels, splines, smoothing.",
    19: "Resampling to estimate sampling distributions — the bootstrap and its variants.",
    20: "Procedures where you choose when to stop based on the data so far.",
}


def stub_html(num, title, sections, prev_link, next_link, tagline):
    sec_li = "\n".join(
        f'      <li>{s["num"]} — {s["title"]}</li>' for s in sections
    ) or "      <li>(sections to be listed)</li>"
    prev_html = (
        f'<a href="{prev_link["href"]}"><span class="label">← Previous</span>'
        f'<span class="title">{prev_link["title"]}</span></a>'
        if prev_link else
        '<a href="../index.html"><span class="label">Up</span><span class="title">Contents</span></a>'
    )
    next_html = (
        f'<a href="{next_link["href"]}" class="next"><span class="label">Next →</span>'
        f'<span class="title">{next_link["title"]}</span></a>'
        if next_link else
        '<a href="../index.html" class="next"><span class="label">Up</span><span class="title">Contents</span></a>'
    )
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Ch {num} - {title} - Theoretical Statistics</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,wght@0,400;0,600;0,700;1,400&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css" />
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
<link rel="stylesheet" href="../css/style.css" />
</head>
<body>
<header class="site-header">
  <a class="brand" href="../index.html">Theoretical Statistics <small>a slow reading guide</small></a>
  <nav>
    <a href="../index.html">Contents</a>
    <button class="theme-toggle" aria-label="toggle theme">Dark</button>
  </nav>
</header>

<main class="layout">
  <aside class="sidebar">
    <h4>Chapter {num}</h4>
    <ol>
      <li><a href="#overview">Overview</a></li>
      <li><a href="#sections">Section list</a></li>
      <li><a href="#status">Status</a></li>
    </ol>
  </aside>

  <article class="content">
    <section class="hero">
      <div class="kicker">Chapter {num}</div>
      <h1>{title}</h1>
      <p class="subtitle">{tagline}</p>
      <div class="meta"><span>Status: draft scaffold</span></div>
    </section>

    <h2 id="overview">Overview</h2>
    <p>
      This page is a scaffold. The slow, careful explainer for this chapter is on the way — it will follow the same
      style as <a href="ch01.html">Chapter 1</a>: every definition unpacked, every "obvious" step spelled out,
      with intuition boxes, worked examples, and pause checkpoints.
    </p>
    <p>
      In the meantime, here is the section structure of this chapter so you can see what's coming.
    </p>

    <h2 id="sections">Section list</h2>
    <ul>
{sec_li}
    </ul>

    <h2 id="status">Status</h2>
    <div class="box pause">
      <span class="box-label">Coming next</span>
      <p>
        Say the word and this chapter's full explainer will be written. Reading the chapters in order is recommended,
        since later chapters lean heavily on earlier ones.
      </p>
    </div>

    <nav class="chapter-nav">
      {prev_html}
      {next_html}
    </nav>
  </article>
</main>

<script src="../js/main.js"></script>
</body>
</html>
'''


for num in range(2, 21):
    if num not in chapter_data:
        continue
    title = chapter_data[num]["title"]
    sections = chapter_data[num]["sections"]
    tagline = chapter_taglines.get(num, "")
    prev_link = {
        "href": f"ch{num-1:02d}.html",
        "title": f"{num-1}. {chapter_data[num-1]['title']}" if num-1 in chapter_data else "Contents",
    }
    if num < 20 and (num + 1) in chapter_data:
        next_link = {"href": f"ch{num+1:02d}.html", "title": f"{num+1}. {chapter_data[num+1]['title']}"}
    else:
        next_link = None
    html = stub_html(num, title, sections, prev_link, next_link, tagline)
    out = os.path.join(OUT_DIR, f"ch{num:02d}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {out}")

print("done")
