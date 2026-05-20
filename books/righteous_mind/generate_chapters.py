#!/usr/bin/env python3
"""
generate_chapters.py
Reads pre-extracted .txt chapter files and generates structured HTML pages
for "The Righteous Mind" — The Righteous Mind book site.
"""

import os, re, html as html_module

BASE     = "/Users/shamitfatin/Codefile/Math/books/righteous_mind"
TEXT_DIR = f"{BASE}/chapter_texts"
HTML_DIR = f"{BASE}/chapters"

# ---------------------------------------------------------------------------
# Chapter manifest
# ---------------------------------------------------------------------------

CHAPTERS = [
    dict(slug="intro",      page="intro",      num=None, title="Introduction",
         part=None,
         prev=None,
         next=("ch01", "1. Where Does Morality Come From?")),
    dict(slug="ch01",       page="ch01",       num=1,    title="Where Does Morality Come From?",
         part="Part I · Intuitions Come First, Strategic Reasoning Second",
         prev=("intro", "Introduction"),
         next=("ch02", "2. The Intuitive Dog and Its Rational Tail")),
    dict(slug="ch02",       page="ch02",       num=2,    title="The Intuitive Dog and Its Rational Tail",
         part="Part I · Intuitions Come First, Strategic Reasoning Second",
         prev=("ch01", "1. Where Does Morality Come From?"),
         next=("ch03", "3. Elephants Rule")),
    dict(slug="ch03",       page="ch03",       num=3,    title="Elephants Rule",
         part="Part I · Intuitions Come First, Strategic Reasoning Second",
         prev=("ch02", "2. The Intuitive Dog and Its Rational Tail"),
         next=("ch04", "4. Vote for Me (Here's Why)")),
    dict(slug="ch04",       page="ch04",       num=4,    title="Vote for Me (Here's Why)",
         part="Part I · Intuitions Come First, Strategic Reasoning Second",
         prev=("ch03", "3. Elephants Rule"),
         next=("ch05", "5. Beyond WEIRD Morality")),
    dict(slug="ch05",       page="ch05",       num=5,    title="Beyond WEIRD Morality",
         part="Part II · There's More to Morality than Harm and Fairness",
         prev=("ch04", "4. Vote for Me (Here's Why)"),
         next=("ch06", "6. Taste Buds of the Righteous Mind")),
    dict(slug="ch06",       page="ch06",       num=6,    title="Taste Buds of the Righteous Mind",
         part="Part II · There's More to Morality than Harm and Fairness",
         prev=("ch05", "5. Beyond WEIRD Morality"),
         next=("ch07", "7. The Moral Foundations of Politics")),
    dict(slug="ch07",       page="ch07",       num=7,    title="The Moral Foundations of Politics",
         part="Part II · There's More to Morality than Harm and Fairness",
         prev=("ch06", "6. Taste Buds of the Righteous Mind"),
         next=("ch08", "8. The Conservative Advantage")),
    dict(slug="ch08",       page="ch08",       num=8,    title="The Conservative Advantage",
         part="Part II · There's More to Morality than Harm and Fairness",
         prev=("ch07", "7. The Moral Foundations of Politics"),
         next=("ch09", "9. Why Are We So Groupish?")),
    dict(slug="ch09",       page="ch09",       num=9,    title="Why Are We So Groupish?",
         part="Part III · Morality Binds and Blinds",
         prev=("ch08", "8. The Conservative Advantage"),
         next=("ch10", "10. The Hive Switch")),
    dict(slug="ch10",       page="ch10",       num=10,   title="The Hive Switch",
         part="Part III · Morality Binds and Blinds",
         prev=("ch09", "9. Why Are We So Groupish?"),
         next=("ch11", "11. Religion Is a Team Sport")),
    dict(slug="ch11",       page="ch11",       num=11,   title="Religion Is a Team Sport",
         part="Part III · Morality Binds and Blinds",
         prev=("ch10", "10. The Hive Switch"),
         next=("ch12", "12. Can't We All Disagree More Constructively?")),
    dict(slug="ch12",       page="ch12",       num=12,   title="Can't We All Disagree More Constructively?",
         part="Part III · Morality Binds and Blinds",
         prev=("ch11", "11. Religion Is a Team Sport"),
         next=("conclusion", "Conclusion")),
    dict(slug="conclusion", page="conclusion", num=None, title="Conclusion",
         part=None,
         prev=("ch12", "12. Can't We All Disagree More Constructively?"),
         next=None),
]

# ---------------------------------------------------------------------------
# Running headers to strip (appear at top of each PDF page)
# ---------------------------------------------------------------------------

_HEADER_PATTERNS = [
    r"^The Righteous Mind$",
    r"^Intuitions Come First, Strategic Reasoning Second$",
    r"^There.s More to Morality than Harm and Fairness$",
    r"^Morality Binds and Blinds$",
    r"^Introduction$",
    r"^Conclusion$",
    r"^Where Does Morality Come From\?$",
    r"^The Intuitive Dog and Its Rational Tail$",
    r"^Elephants Rule$",
    r"^Vote for Me \(Here.s Why\)$",
    r"^Beyond WEIRD Morality$",
    r"^Taste Buds of the Righteous Mind$",
    r"^The Moral Foundations of Politics$",
    r"^The Conservative Advantage$",
    r"^Why Are We So Groupish\?$",
    r"^The Hive Switch$",
    r"^Religion Is a Team Sport$",
    r"^Can.t We All Disagree More Constructively\?$",
    r"^Central Metaphor$",
]
_HEADER_RE = re.compile("|".join(_HEADER_PATTERNS))

# ---------------------------------------------------------------------------
# OCR ligature fixes  (ff / fi / fl ligatures rendered as missing chars)
# ---------------------------------------------------------------------------

_OCR = [
    # ff ligature
    (r'\bdi erent',         'different'),
    (r'\bdi ers\b',         'differs'),
    (r'\bdi er\b',          'differ'),
    (r'\bdi erence',        'difference'),
    (r'\bdi erences',       'differences'),
    (r'\be ect',            'effect'),
    (r'\be ective',         'effective'),
    (r'\be ectively',       'effectively'),
    (r'\be ort',            'effort'),
    (r'\be orts',           'efforts'),
    (r'\ba ect',            'affect'),
    (r'\ba ected',          'affected'),
    (r'\ba ection',         'affection'),
    (r'\bo er\b',           'offer'),
    (r'\bo ers\b',          'offers'),
    (r'\bo ered\b',         'offered'),
    (r'\bo ering',          'offering'),
    (r'\bo ice\b',          'office'),
    (r'\bo ices\b',         'offices'),
    (r'\bo icer',           'officer'),
    (r'\bo cer',            'officer'),   # ffi dropped entirely
    (r'\bo icial',          'official'),
    (r'\bsu er\b',          'suffer'),
    (r'\bsu ers\b',         'suffers'),
    (r'\bsu ered\b',        'suffered'),
    (r'\bsu ering',         'suffering'),
    (r'\bbu er',            'buffer'),
    (r'\bpro t\b',          'profit'),
    (r'\bpro ts\b',         'profits'),
    (r'\bpro table',        'profitable'),
    (r'\bpro le\b',         'profile'),
    (r'\bbene t\b',         'benefit'),
    (r'\bbene ts\b',        'benefits'),
    (r'\bre ect',           'reflect'),
    (r'\bcon ict',          'conflict'),
    (r'\bcon icts',         'conflicts'),
    (r'\bshu le',           'shuffle'),
    (r'\bra le',            'raffle'),
    (r'\bsni ',             'sniff'),
    # ffi ligature  (fi part drops, leaves space)
    (r'\bsu cient',         'sufficient'),
    (r'\bsu ciency',        'sufficiency'),
    (r'\binsu cient',       'insufficient'),
    (r'\bef cient',         'efficient'),
    (r'\bef ciency',        'efficiency'),
    (r'\binef cient',       'inefficient'),
    (r'\bpro cient',        'proficient'),
    (r'\bde cient',         'deficient'),
    (r'\bde ciency',        'deficiency'),
    (r'\bde cit\b',         'deficit'),
    (r'\bde cits\b',        'deficits'),
    (r'\btra c\b',          'traffic'),
    (r'\bdi cult',          'difficult'),
    (r'\bdi culty',         'difficulty'),
    (r'\bdi culties',       'difficulties'),
    # fi ligature
    (r'\b rst\b',           'first'),
    (r'\b nd\b',            'find'),
    (r'\b nds\b',           'finds'),
    (r'\b nding\b',         'finding'),
    (r'\b ndings\b',        'findings'),
    (r'\b ght\b',           'fight'),
    (r'\b ghts\b',          'fights'),
    (r'\b ghting\b',        'fighting'),
    (r'\b eld\b',           'field'),
    (r'\b elds\b',          'fields'),
    (r'\b erce\b',          'fierce'),
    (r'\b ll\b',            'fill'),
    (r'\b lled\b',          'filled'),
    (r'\b lling\b',         'filling'),
    (r'\b lter\b',          'filter'),
    (r'\b lters\b',         'filters'),
    (r'\b gure\b',          'figure'),
    (r'\b gures\b',         'figures'),
    (r'\b rm\b',            'firm'),
    (r'\b rmly\b',          'firmly'),
    (r'\bsigni cant\b',     'significant'),
    (r'\bsigni cance\b',    'significance'),
    (r'\bsigni cantly\b',   'significantly'),
    (r'\bsigni cant\b',     'significant'),
    (r'\bspeci c\b',        'specific'),
    (r'\bspeci cally\b',    'specifically'),
    (r'\bspeci city\b',     'specificity'),
    (r'\bsci enti c\b',     'scientific'),
    (r'\bmodi ed\b',        'modified'),
    (r'\bjusti ed\b',       'justified'),
    (r'\bjusti cation\b',   'justification'),
    (r'\bjusti fy\b',       'justify'),
    (r'\bgrati cation\b',   'gratification'),
    (r'\bveri ed\b',        'verified'),
    (r'\bveri cation\b',    'verification'),
    (r'\brati cation\b',    'ratification'),
    (r'\bcodi ed\b',        'codified'),
    (r'\bclassi ed\b',      'classified'),
    (r'\bclassi cation\b',  'classification'),
    (r'\bampli ed\b',       'amplified'),
    (r'\bampli er\b',       'amplifier'),
    (r'\bmagni ed\b',       'magnified'),
    (r'\bsatis ed\b',       'satisfied'),
    (r'\bsatis ying\b',     'satisfying'),
    (r'\bsatis action\b',   'satisfaction'),
    (r'\bquali ed\b',       'qualified'),
    (r'\bquali cation\b',   'qualification'),
    (r'\bpuri ed\b',        'purified'),
    (r'\bpuri cation\b',    'purification'),
    (r'\bsimpli ed\b',      'simplified'),
    (r'\barti cial\b',      'artificial'),
    (r'\barti cially\b',    'artificially'),
    (r'\bsuperficial\b',    'superficial'),   # already correct, skip
    (r'\bsuperficial',      'superficial'),
    (r'\bsure re\b',        'surefire'),
    (r'\bback re\b',        'backfire'),
    (r'\bcampfire\b',       'campfire'),      # already correct
    (r'\bgun re\b',         'gunfire'),
    (r'\bcross re\b',       'crossfire'),
    (r'\bwild re\b',        'wildfire'),
    (r'\bcounterfeit',      'counterfeit'),
    (r'\bforti ed\b',       'fortified'),
    (r'\bfalsi ed\b',       'falsified'),
    (r'\bfalsi cation\b',   'falsification'),
    # fl ligature
    (r'\b oor\b',           'floor'),
    (r'\b oors\b',          'floors'),
    (r'\b ow\b',            'flow'),
    (r'\b ows\b',           'flows'),
    (r'\b ower\b',          'flower'),
    (r'\b owers\b',         'flowers'),
    (r'\b oat\b',           'float'),
    (r'\b ight\b',          'flight'),
    (r'\b ights\b',         'flights'),
    (r'\b ag\b',            'flag'),
    (r'\b ags\b',           'flags'),
    (r'\b aw\b',            'flaw'),
    (r'\b aws\b',           'flaws'),
    (r'\b at\b',            'flat'),
    (r'\b ex\b',            'flex'),
    (r'\b exible\b',        'flexible'),
    (r'\b exibility\b',     'flexibility'),
    (r'\b esh\b',           'flesh'),
    (r'\b ock\b',           'flock'),
    (r'\b ood\b',           'flood'),
    (r'\b uid\b',           'fluid'),
    (r'\b uent\b',          'fluent'),
    (r'\b uency\b',         'fluency'),
]

# ---------------------------------------------------------------------------
# Heading helpers (defined first — used by both clean_text and render_chapter)
# ---------------------------------------------------------------------------

def _strip_number_prefix(text):
    return re.sub(r'^\d+\.\s*', '', text)

def is_section_heading(text):
    """Detect ALL-CAPS section headings (numbered '1. HEADING' or plain)."""
    s = _strip_number_prefix(text.strip())
    if len(s) > 90 or len(s) < 4:
        return False
    if s.endswith(('.', ',', ';', ':')):
        return False
    alpha = [c for c in s if c.isalpha()]
    if len(alpha) < 3:
        return False
    return sum(1 for c in alpha if c.isupper()) / len(alpha) >= 0.80

# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

def clean_text(raw, ch_title=None):
    """Strip running headers/page numbers, fix ligature OCR artifacts."""
    pages = raw.split('\x0c')
    out_pages = []
    for page in pages:
        lines = page.split('\n')
        kept = []
        for line in lines:
            s = line.strip()
            if not s:
                kept.append(line)
                continue
            if re.match(r'^\d+$', s):              # bare page number
                continue
            if _HEADER_RE.match(s):                # running header
                continue
            if re.match(r'^(ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE)$', s):
                continue
            if re.match(r'^PART (I{1,3}|IV|V{1,3})$', s):
                continue
            if ch_title and s == ch_title:         # strip chapter title line
                continue
            kept.append(line)
        # Insert blank lines around ALL-CAPS heading lines so split_paragraphs
        # separates them correctly (headings often share a page with body text)
        spaced = []
        for line in kept:
            if is_section_heading(line.strip()):
                spaced.extend(['', line, ''])
            else:
                spaced.append(line)
        out_pages.append('\n'.join(spaced))

    text = '\n'.join(out_pages)

    # Fix hyphenated line-breaks: word- \n word → wordword
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)

    # Remove inline footnote superscripts: word1 → word (digit(s) glued to a word char before whitespace)
    text = re.sub(r'(?<=\w)(\d{1,3})(?=\s)', r' ', text)
    text = re.sub(r'(?<=\w)(\d{1,3})$',      r'',  text, flags=re.MULTILINE)

    # Apply ligature fixes
    for pat, rep in _OCR:
        text = re.sub(pat, rep, text)

    return text


# ---------------------------------------------------------------------------
# Paragraph / section parsing
# ---------------------------------------------------------------------------

def split_paragraphs(text):
    """Split on blank lines → list of normalised paragraph strings."""
    blocks = re.split(r'\n\s*\n', text)
    result = []
    for b in blocks:
        b = ' '.join(b.split()).strip()
        if b:
            result.append(b)
    return result




def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>{title_tag}</title>
<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,wght@0,400;0,600;0,700;1,400&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet"/>
<link href="/css/style.css" rel="stylesheet"/><link href="/css/comments.css" rel="stylesheet"/><link href="/css/tts.css" rel="stylesheet"/>
</head>"""

def esc(s):
    return html_module.escape(s, quote=False)


def render_chapter(ch, paragraphs):
    page = ch['page']
    cid  = [10]       # mutable counter

    def next_cid():
        v = cid[0]; cid[0] += 10; return f'{page}-{v:04d}'

    # ---- parse sections ----
    sections     = []   # [(heading_str | None, [para, ...])]
    sidebar_items = []
    cur_head  = None
    cur_paras = []

    for para in paragraphs:
        if is_section_heading(para):
            sections.append((cur_head, cur_paras))
            cur_head  = para
            cur_paras = []
            sidebar_items.append((slugify(para), para.title()))
        else:
            cur_paras.append(para)
    sections.append((cur_head, cur_paras))

    # ---- article body ----
    body_parts = []
    if ch['part']:
        body_parts.append(f'<div class="kicker">{esc(ch["part"])}</div>')
    body_parts.append(f'<h1>{esc(ch["title"])}</h1>')

    for heading, paras in sections:
        if heading:
            slug = slugify(heading)
            body_parts.append(
                f'<h2 id="{slug}" data-cid="{next_cid()}">{esc(heading.title())}</h2>'
            )
        for para in paras:
            body_parts.append(f'<p data-cid="{next_cid()}">{esc(para)}</p>')

    article_html = '\n'.join(body_parts)

    # ---- sidebar ----
    if sidebar_items:
        sidebar_ol = '\n'.join(
            f'<li><a href="#{s}">{esc(l)}</a></li>' for s, l in sidebar_items
        )
    else:
        sidebar_ol = ''

    sidebar_label = f'Chapter {ch["num"]}' if ch['num'] else esc(ch['title'])

    # ---- nav ----
    prev_html = next_html = ''
    if ch['prev']:
        ps, pt = ch['prev']
        prev_html = f'<a class="prev" href="{ps}.html"><span class="label">← Prev</span><span class="title">{esc(pt)}</span></a>'
    if ch['next']:
        ns, nt = ch['next']
        next_html = f'<a class="next" href="{ns}.html"><span class="label">Next →</span><span class="title">{esc(nt)}</span></a>'

    # ---- title tag ----
    t = esc(ch['title'])
    title_tag = f'Ch {ch["num"]} — {t} · The Righteous Mind' if ch['num'] else f'{t} · The Righteous Mind'

    return f"""{HEAD.format(title_tag=title_tag)}
<body data-book="righteous_mind" data-page="{page}">
<header class="site-header">
<a class="home-btn" href="/">Home</a>
<a class="brand" href="/books/righteous_mind/">The Righteous Mind <small>Jonathan Haidt</small></a>
<nav>
<button aria-label="toggle theme" class="theme-toggle">Dark</button>
</nav>
</header>
<main class="layout">
<aside class="sidebar">
<h4>{sidebar_label}</h4>
<ol>
{sidebar_ol}
</ol>
</aside>
<article class="content">
{article_html}
</article>
</main>
<nav class="chapter-nav">
{prev_html}
{next_html}
</nav>
<script src="/js/main.js"></script><script src="/js/comments.js"></script><script src="/js/tts.js"></script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(HTML_DIR, exist_ok=True)
    stats = []

    for ch in CHAPTERS:
        txt_path = f"{TEXT_DIR}/{ch['slug']}.txt"
        with open(txt_path, encoding='utf-8') as f:
            raw = f.read()

        cleaned    = clean_text(raw, ch_title=ch['title'])
        paragraphs = split_paragraphs(cleaned)
        html_out   = render_chapter(ch, paragraphs)

        out_path = f"{HTML_DIR}/{ch['slug']}.html"
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html_out)

        n_cid = html_out.count('data-cid=')
        n_h2  = html_out.count('<h2 ')
        stats.append((ch['slug'], len(html_out), n_cid, n_h2))
        print(f"  {ch['slug']:12s}  {len(html_out):>8,} bytes  {n_cid:3d} blocks  {n_h2:2d} sections")

    print(f"\n✓ {len(stats)} files written to {HTML_DIR}/")


if __name__ == '__main__':
    main()
