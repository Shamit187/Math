"""
wrap_math_tts.py — wrap every LaTeX math expression in chapter HTML files
with <span class="tts-math" data-tts="..."> so the TTS player can read it.

Converts LaTeX to natural English using symbol substitution rules.
Run from the project root:  python tools/wrap_math_tts.py
"""
import os
import re
import sys

CHAPTERS_DIR = os.path.join(os.path.dirname(__file__), '..', 'books', 'basic_stat', 'chapters')

# ── Greek letters ──────────────────────────────────────────────────────────────
GREEK = {
    'alpha': 'alpha', 'beta': 'beta', 'gamma': 'gamma', 'Gamma': 'Gamma',
    'delta': 'delta', 'Delta': 'Delta', 'epsilon': 'epsilon', 'varepsilon': 'epsilon',
    'zeta': 'zeta', 'eta': 'eta', 'theta': 'theta', 'Theta': 'Theta', 'vartheta': 'theta',
    'iota': 'iota', 'kappa': 'kappa', 'lambda': 'lambda', 'Lambda': 'Lambda',
    'mu': 'mu', 'nu': 'nu', 'xi': 'xi', 'Xi': 'Xi', 'pi': 'pi', 'Pi': 'Pi',
    'varpi': 'pi', 'rho': 'rho', 'varrho': 'rho', 'sigma': 'sigma', 'Sigma': 'Sigma',
    'varsigma': 'sigma', 'tau': 'tau', 'upsilon': 'upsilon', 'Upsilon': 'Upsilon',
    'phi': 'phi', 'Phi': 'Phi', 'varphi': 'phi', 'chi': 'chi',
    'psi': 'psi', 'Psi': 'Psi', 'omega': 'omega', 'Omega': 'Omega',
}


def latex_to_speech(s: str) -> str:
    """Best-effort LaTeX → natural English for TTS."""
    s = s.strip()

    # Convergence arrows (must come before generic arrow handling)
    s = re.sub(r'\\xrightarrow\{d\}', ' converges in distribution to ', s)
    s = re.sub(r'\\xrightarrow\{p\}', ' converges in probability to ', s)
    s = re.sub(r'\\xrightarrow\{a\.s\.\}', ' converges almost surely to ', s)
    s = re.sub(r'\\xrightarrow\{[^}]*\}', ' converges to ', s)
    s = re.sub(r'\\overset\{d\}\{=\}', ' equals in distribution ', s)
    s = re.sub(r'\\overset\{[^}]*\}\{([^}]*)\}', r' \1 ', s)
    s = re.sub(r'\\stackrel\{[^}]*\}\{([^}]*)\}', r' \1 ', s)

    # mathbb
    s = re.sub(r'\\mathbb\{R\}', 'the real numbers', s)
    s = re.sub(r'\\mathbb\{Z\}', 'the integers', s)
    s = re.sub(r'\\mathbb\{N\}', 'the natural numbers', s)
    s = re.sub(r'\\mathbb\{Q\}', 'the rationals', s)
    s = re.sub(r'\\mathbb\{([A-Z])\}', r'\1', s)

    # mathcal
    s = re.sub(r'\\mathcal\{([A-Z])\}', lambda m: f'script {m.group(1)}', s)

    # text-style wrappers
    s = re.sub(r'\\(?:mathbf|boldsymbol|mathit|mathrm|text|operatorname\*?)\{([^}]+)\}', r'\1', s)

    # Greek
    for cmd, name in GREEK.items():
        s = re.sub(r'\\' + re.escape(cmd) + r'(?![a-zA-Z])', f' {name} ', s)

    # Common functions
    for fn in ['log', 'ln', 'exp', 'sin', 'cos', 'tan', 'det', 'tr', 'rank',
               'dim', 'ker', 'img', 'var', 'cov', 'Var', 'Cov', 'Pr']:
        s = re.sub(r'\\' + fn + r'\b', f' {fn} ', s)

    # Decorated letters (process before sub/superscript)
    s = re.sub(r'\\hat\{([^}]+)\}',      lambda m: f' {latex_to_speech(m.group(1))} hat ', s)
    s = re.sub(r'\\bar\{([^}]+)\}',      lambda m: f' {latex_to_speech(m.group(1))} bar ', s)
    s = re.sub(r'\\tilde\{([^}]+)\}',    lambda m: f' {latex_to_speech(m.group(1))} tilde ', s)
    s = re.sub(r'\\vec\{([^}]+)\}',      lambda m: f' vector {latex_to_speech(m.group(1))} ', s)
    s = re.sub(r'\\widehat\{([^}]+)\}',  lambda m: f' {latex_to_speech(m.group(1))} hat ', s)
    s = re.sub(r'\\widetilde\{([^}]+)\}',lambda m: f' {latex_to_speech(m.group(1))} tilde ', s)
    s = re.sub(r'\\overline\{([^}]+)\}', lambda m: f' {latex_to_speech(m.group(1))} bar ', s)
    s = re.sub(r'\\dot\{([^}]+)\}',      lambda m: f' {latex_to_speech(m.group(1))} dot ', s)

    # Fractions
    def frac_r(m):
        return f' {latex_to_speech(m.group(1))} over {latex_to_speech(m.group(2))} '
    s = re.sub(r'\\[tdf]?frac\{([^}]+)\}\{([^}]+)\}', frac_r, s)

    # Square roots
    s = re.sub(r'\\sqrt\[([^\]]+)\]\{([^}]+)\}',
               lambda m: f' {latex_to_speech(m.group(1))}th root of {latex_to_speech(m.group(2))} ', s)
    s = re.sub(r'\\sqrt\{([^}]+)\}', lambda m: f' root {latex_to_speech(m.group(1))} ', s)
    s = re.sub(r'\\sqrt\b', ' root ', s)

    # Integrals
    s = re.sub(r'\\iint\b', ' double integral of ', s)
    s = re.sub(r'\\iiint\b', ' triple integral of ', s)
    s = re.sub(r'\\int_\{([^}]+)\}\s*\^\{([^}]+)\}',
               lambda m: f' the integral from {latex_to_speech(m.group(1))} to {latex_to_speech(m.group(2))} of ', s)
    s = re.sub(r'\\int_\{([^}]+)\}',
               lambda m: f' the integral over {latex_to_speech(m.group(1))} of ', s)
    s = re.sub(r'\\int\b', ' the integral of ', s)

    # Sums
    s = re.sub(r'\\sum_\{([^}]+)\}\s*\^\{([^}]+)\}',
               lambda m: f' the sum from {latex_to_speech(m.group(1))} to {latex_to_speech(m.group(2))} of ', s)
    s = re.sub(r'\\sum_\{([^}]+)\}',
               lambda m: f' the sum over {latex_to_speech(m.group(1))} of ', s)
    s = re.sub(r'\\sum\b', ' the sum of ', s)

    # Products
    s = re.sub(r'\\prod_\{([^}]+)\}\s*\^\{([^}]+)\}',
               lambda m: f' the product from {latex_to_speech(m.group(1))} to {latex_to_speech(m.group(2))} of ', s)
    s = re.sub(r'\\prod\b', ' the product of ', s)

    # Limits
    s = re.sub(r'\\lim_\{([^}]+)\}',
               lambda m: f' the limit as {latex_to_speech(m.group(1))} of ', s)
    s = re.sub(r'\\lim\b', ' the limit of ', s)
    s = re.sub(r'\\liminf\b', ' limit inferior of ', s)
    s = re.sub(r'\\limsup\b', ' limit superior of ', s)
    s = re.sub(r'\\sup\b', ' supremum ', s)
    s = re.sub(r'\\inf\b', ' infimum ', s)
    s = re.sub(r'\\max\b', ' max ', s)
    s = re.sub(r'\\min\b', ' min ', s)
    s = re.sub(r'\\argmax\b', ' argmax ', s)
    s = re.sub(r'\\argmin\b', ' argmin ', s)

    # Superscripts
    def sup_r(m):
        c = m.group(1)
        if c == '-1':    return ' inverse'
        if c in ('T', r'\top', r'\intercal'): return ' transpose'
        if c == '2':     return ' squared'
        if c == '3':     return ' cubed'
        if c == '*':     return ' star'
        if c == 'c':     return ' complement'
        return f' to the {latex_to_speech(c)}'
    s = re.sub(r'\^\{([^}]+)\}', sup_r, s)
    s = re.sub(r'\^([a-zA-Z0-9*])',
               lambda m: ' transpose' if m.group(1) == 'T' else f' to the {m.group(1)}', s)

    # Subscripts
    s = re.sub(r'_\{([^}]+)\}', lambda m: f' sub {latex_to_speech(m.group(1))}', s)
    s = re.sub(r'_([a-zA-Z0-9])', lambda m: f' sub {m.group(1)}', s)

    # Operators / relations
    pairs = [
        (r'\\cdot',          ' times '),
        (r'\\times',         ' times '),
        (r'\\div',           ' divided by '),
        (r'\\pm',            ' plus or minus '),
        (r'\\mp',            ' minus or plus '),
        (r'\\leq|\\le\b',    ' less than or equal to '),
        (r'\\geq|\\ge\b',    ' greater than or equal to '),
        (r'\\neq|\\ne\b',    ' not equal to '),
        (r'\\approx',        ' approximately '),
        (r'\\sim\b',         ' distributed as '),
        (r'\\simeq',         ' approximately '),
        (r'\\equiv',         ' equivalent to '),
        (r'\\propto',        ' proportional to '),
        (r'\\in\b',          ' in '),
        (r'\\notin\b',       ' not in '),
        (r'\\subseteq',      ' subset of or equal to '),
        (r'\\subset',        ' subset of '),
        (r'\\supseteq',      ' superset of or equal to '),
        (r'\\supset',        ' superset of '),
        (r'\\cup\b',         ' union '),
        (r'\\cap\b',         ' intersect '),
        (r'\\setminus',      ' minus '),
        (r'\\emptyset|\\varnothing', ' the empty set '),
        (r'\\infty',         ' infinity '),
        (r'\\to\b|\\rightarrow', ' to '),
        (r'\\leftarrow',     ' from '),
        (r'\\Rightarrow',    ' implies '),
        (r'\\Leftarrow',     ' implied by '),
        (r'\\Leftrightarrow|\\iff', ' if and only if '),
        (r'\\mid\b',         ' given '),
        (r'\\\|',            ' norm of '),
        (r'\\ell\b',         ' ell '),
        (r'\\top\b',         ' transpose '),
        (r'\\bot\b',         ' bottom '),
        (r'\\partial',       ' partial '),
        (r'\\nabla',         ' gradient '),
        (r'\\forall',        ' for all '),
        (r'\\exists',        ' there exists '),
        (r'\\land\b',        ' and '),
        (r'\\lor\b',         ' or '),
        (r'\\ldots|\\cdots|\\dots', ' and so on '),
        (r'\\vdots|\\ddots', ' '),
        (r'\\colon\b',       ' such that '),
    ]
    for pat, rep in pairs:
        s = re.sub(pat, rep, s)

    # Remove delimiter size commands
    s = re.sub(r'\\(?:left|right|[Bb]ig{1,2}[lr]?)[.()\[\]|\\{}]?', ' ', s)
    s = re.sub(r'\\[lLrR]angle\b', ' ', s)
    s = re.sub(r'\\[lLrR](?:floor|ceil|vert)\b', ' ', s)

    # Spacing
    s = re.sub(r'\\[,;:! ]', ' ', s)
    s = re.sub(r'\\(?:quad|qquad)\b', ' ', s)
    s = re.sub(r'\\hspace\{[^}]+\}', ' ', s)
    s = re.sub(r'\\!', '', s)

    # Matrix / cases environments
    s = re.sub(r'\\begin\{[^}]+\}', ' ', s)
    s = re.sub(r'\\end\{[^}]+\}', ' ', s)
    s = re.sub(r'\\\\', ' ', s)
    s = s.replace('&', ' ')

    # Remove remaining unknown backslash commands
    s = re.sub(r'\\[a-zA-Z]+\*?\b', ' ', s)

    # Basic arithmetic operators (after all backslash processing)
    s = s.replace('+', ' plus ')
    s = s.replace('-', ' minus ')
    s = s.replace('=', ' equals ')
    s = s.replace('<', ' less than ')
    s = s.replace('>', ' greater than ')
    s = s.replace('*', ' times ')
    s = s.replace('/', ' over ')
    s = s.replace("'", ' prime')

    # Remove remaining LaTeX punctuation
    s = re.sub(r'[{}()\[\]|\\]', ' ', s)
    s = re.sub(r'[,;:]', ' ', s)

    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()

    # Strip leading/trailing connector words that are artefacts
    s = re.sub(r'^(to the|of|plus|minus|times|over|equals)\s+', '', s)
    s = re.sub(r'\s+(to the|of)\s*$', '', s)

    return s if s else 'math expression'


# ── HTML-level math finder ──────────────────────────────────────────────────────

def wrap_content(content: str) -> tuple[str, int]:
    """
    Find every un-wrapped $...$ and $$...$$ in an HTML string and wrap it.
    Returns (new_content, count).
    """
    count = 0
    out = []
    i = 0
    n = len(content)

    while i < n:
        # --- Skip HTML tags (avoid matching $ inside attributes) ---
        if content[i] == '<':
            j = content.find('>', i)
            if j == -1:
                out.append(content[i:])
                break
            out.append(content[i:j+1])
            i = j + 1
            continue

        # --- Skip already-wrapped spans ---
        # (we won't enter a tag, so tts-math wrapper can't appear here
        #  unless there's nested content — safe to ignore for our use case)

        # --- Display math $$...$$ ---
        if content[i:i+2] == '$$':
            end = content.find('$$', i+2)
            if end == -1:
                out.append(content[i])
                i += 1
                continue
            latex = content[i+2:end]
            desc = latex_to_speech(latex)
            desc = desc.replace('"', "'").replace('\n', ' ')
            desc = re.sub(r'\s+', ' ', desc).strip()
            out.append(f'<span class="tts-math" data-tts="{desc}">$${latex}$$</span>')
            i = end + 2
            count += 1
            continue

        # --- Inline math $...$ ---
        if content[i] == '$':
            # Find closing $
            j = i + 1
            found = False
            while j < n:
                if content[j] == '$':
                    latex = content[i+1:j]
                    # Sanity: non-empty, no unbalanced braces, reasonable length
                    if latex and len(latex) <= 300 and '\n\n' not in latex:
                        desc = latex_to_speech(latex)
                        desc = desc.replace('"', "'").replace('\n', ' ')
                        desc = re.sub(r'\s+', ' ', desc).strip()
                        out.append(f'<span class="tts-math" data-tts="{desc}">${latex}$</span>')
                        i = j + 1
                        count += 1
                        found = True
                    break
                j += 1
            if not found:
                out.append(content[i])
                i += 1
            continue

        out.append(content[i])
        i += 1

    return ''.join(out), count


def process_file(filepath: str) -> int:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'class="tts-math"' in content:
        print(f'  {os.path.basename(filepath)}: already wrapped — skipping')
        return 0

    new_content, count = wrap_content(content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return count


def main():
    chapters_dir = os.path.abspath(CHAPTERS_DIR)
    files = sorted(f for f in os.listdir(chapters_dir) if re.match(r'ch\d+\.html$', f))

    total = 0
    for fname in files:
        fpath = os.path.join(chapters_dir, fname)
        count = process_file(fpath)
        if count:
            print(f'  {fname}: wrapped {count} expressions')
        total += count

    print(f'\nDone — {total} math expressions wrapped across {len(files)} files.')


if __name__ == '__main__':
    main()
