#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
search_fonts.py — search the available font library (data/fonts.csv) by
mood/style/scenario keywords.

Font rule: drafts may only use fonts from data/fonts.csv (the sole legal font
source, self-hosted on BOS), plus a system-font fallback chain. Never pull in
Google Fonts or any other external font CDN.

Query content: mood / style / scenario words (Chinese or English both index). Do NOT put
language or charset words (chinese / cjk / 简体) in the query — use --lang for that; in the
query they match cultural mood tags (calligraphy, festive) instead of the intended style.

Usage:
    python3 scripts/search_fonts.py "<keywords, Chinese or English>" \
        [--usage body|heading] [--lang zh|tc|ja|latin] [-n 5]
    python3 scripts/search_fonts.py --name "得意黑"     # look up a single font by name (exact/substring match)
    python3 scripts/search_fonts.py --list              # whole-library overview (No/name/category/usage/language)

    # example: find a heading font for an "esports tournament" theme
    python3 scripts/search_fonts.py "esports 电竞 aggressive" --usage heading --lang zh
    # example: find a Chinese body font for a Japanese-style healing theme
    python3 scripts/search_fonts.py "japandi 治愈 温柔 lifestyle" --usage body --lang zh

Output: ranked candidates, each with font-family, weights, the full BOS URL,
and a ready-to-paste @font-face snippet.
Exit codes: 0 = results found; 1 = no results or an error.

Search algorithm: BM25 + CJK character bigrams + Latin stemming, standard
library only.
"""

import argparse
import csv
import io
import json
import re
import sys
from collections import defaultdict
from math import log
from pathlib import Path

DATA_CSV = Path(__file__).resolve().parent.parent / "data" / "fonts.csv"
FONT_URL_PREFIX = "https://resource-static.bj.bcebos.com/fonts-skill/"

SEARCH_COLS = [
    "Font_Name_CN", "Font_Name_EN", "Category",
    "Mood_Keywords", "Best_For", "Best_For_CN",
]

# display/handwriting/pixel are highly stylized with extreme strokes; a full
# paragraph in them is tiring, so they are barred from body use
BODY_FORBIDDEN_CATEGORIES = {"display", "handwriting", "pixel"}

LANG_NEEDLE = {"zh": "简体", "tc": "繁体", "ja": "日文", "latin": "西文"}

# Normalize synonymous input: models tend to pass near-synonyms by intuition,
# so the tool should accept them rather than erroring out.
# (display fonts are heading-level by nature; en=latin is the same concept
# under a different name.)
USAGE_ALIASES = {
    "display": "heading", "title": "heading", "headline": "heading", "subhead": "heading",
    "标题": "heading", "大标题": "heading", "小标题": "heading", "副标题": "heading",
    "body": "body", "heading": "heading",
    "text": "body", "paragraph": "body", "copy": "body",
    "正文": "body", "段落": "body", "文字": "body",
}
LANG_ALIASES = {
    "zh": "zh", "cn": "zh", "chinese": "zh", "zh-cn": "zh", "simplified": "zh",
    "简体": "zh", "中文": "zh", "简中": "zh",
    "tc": "tc", "tw": "tc", "zh-tw": "tc", "traditional": "tc",
    "繁体": "tc", "繁中": "tc",
    "ja": "ja", "jp": "ja", "japanese": "ja",
    "日文": "ja", "日语": "ja",
    "latin": "latin", "en": "latin", "english": "latin", "western": "latin", "eu": "latin",
    "西文": "latin", "英文": "latin",
}

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


_STEM_SUFFIXES = [
    ("ational", 3), ("ation", 3), ("ional", 3), ("tion", 4), ("sion", 4),
    ("ment", 4), ("ness", 5), ("ful", 3), ("ing", 3), ("ous", 4),
    ("ive", 4), ("ity", 4), ("al", 4), ("ly", 4), ("er", 4),
    ("ed", 4), ("es", 4), ("s", 3),
]


def _stem(word):
    """Strip a common English suffix when the remaining stem stays long enough."""
    if len(word) <= 3:
        return word
    for suffix, min_stem in _STEM_SUFFIXES:
        if not word.endswith(suffix):
            continue
        stem = word[: -len(suffix)]
        if len(stem) < min_stem:
            continue
        if suffix in ("s", "es") and word[-len(suffix) - 1] == "s":
            continue
        return stem
    return word


def _tokenize(text):
    """CJK character bigrams + Latin stemming (Chinese has no spaces, so
    bigrams preserve recall with zero third-party dependencies)."""
    text = re.sub(r"[^\w\s]", " ", str(text).lower())
    tokens = []
    for seg in re.findall(r"[一-鿿]+|[a-z0-9]+", text):
        if "一" <= seg[0] <= "鿿":
            if len(seg) == 1:
                tokens.append(seg)
            else:
                tokens.extend(seg[i:i + 2] for i in range(len(seg) - 1))
        elif len(seg) > 2:
            tokens.append(_stem(seg))
    return tokens


class BM25:
    """Minimal BM25 ranker over pre-tokenized documents (standard library only)."""

    def __init__(self, k1=1.5, b=0.75):
        """Store the BM25 hyper-parameters and initialize empty index state."""
        self.k1, self.b = k1, b
        self.corpus, self.doc_lengths = [], []
        self.avgdl, self.N = 0, 0
        self.idf = {}

    def fit(self, documents):
        """Tokenize and index the documents, computing per-term IDF."""
        self.corpus = [_tokenize(d) for d in documents]
        self.N = len(self.corpus)
        if not self.N:
            return
        self.doc_lengths = [len(d) for d in self.corpus]
        self.avgdl = sum(self.doc_lengths) / self.N
        dfreq = defaultdict(int)
        for doc in self.corpus:
            for word in set(doc):
                dfreq[word] += 1
        self.idf = {
            w: log((self.N - f + 0.5) / (f + 0.5) + 1) for w, f in dfreq.items()
        }

    def score(self, query):
        """Score every indexed document against the query; returns [(index, score)] descending."""
        qtokens = _tokenize(query)
        scores = []
        for idx, doc in enumerate(self.corpus):
            tf = defaultdict(int)
            for w in doc:
                tf[w] += 1
            s = 0.0
            for t in qtokens:
                if t not in self.idf:
                    continue
                num = tf[t] * (self.k1 + 1)
                den = tf[t] + self.k1 * (
                    1 - self.b + self.b * self.doc_lengths[idx] / self.avgdl
                )
                s += self.idf[t] * num / den
            scores.append((idx, s))
        return sorted(scores, key=lambda x: x[1], reverse=True)


def load_fonts():
    """Load data/fonts.csv into a list of row dicts."""
    with open(DATA_CSV, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def font_url(row, weight=None):
    """URL of the default file; when a weight is given and a template exists,
    build the URL from the template."""
    template = (row.get("CDN_URL_Template") or "").strip()
    if weight and template and "{weight}" in template:
        return FONT_URL_PREFIX + template.replace("{weight}", weight)
    return FONT_URL_PREFIX + (row.get("CDN_URL") or "").strip()


def font_face_snippet(row):
    """Build a ready-to-paste @font-face CSS block for a font row."""
    family = (row.get("Font_Family") or "").strip()
    url = font_url(row)
    ext = url.rsplit(".", 1)[-1].lower()
    fmt = {"woff2": "woff2", "woff": "woff", "ttf": "truetype", "otf": "opentype"}.get(ext)
    src = f'url("{url}")' + (f' format("{fmt}")' if fmt else "")
    return (
        "@font-face {\n"
        f'  font-family: "{family}";\n'
        f"  src: {src};\n"
        "  font-display: swap;\n"
        "}"
    )


def passes_filters(row, usage, lang):
    """Check a font row against the requested --usage/--lang filters."""
    if usage == "body":
        if (row.get("Usage") or "").strip() == "heading":
            return False
        if (row.get("Category") or "").strip() in BODY_FORBIDDEN_CATEGORIES:
            return False
    if usage == "heading" and (row.get("Usage") or "").strip() == "body":
        # Using a body-only font for a heading is legitimate (just switch its
        # weight), so it isn't filtered out
        pass
    if lang:
        if LANG_NEEDLE[lang] not in (row.get("language") or ""):
            return False
    return True


def render(row, rank=None, full=True):
    """full=True (single-font --name lookup, or one confirmed choice) prints the
    full @font-face code block; full=False (search results with multiple
    candidates) prints only the essentials (family/url/valid weight names) and
    leaves the model to assemble the standard @font-face syntax itself — a
    search typically returns 5+ candidates, and putting a code block on every
    one would bury the list under CSS and hide the mood differences between
    candidates.
    """
    lines = []
    head = f"{row.get('Font_Name_CN', '')} / {row.get('Font_Name_EN', '')}"
    lines.append(f"### {'#%d ' % rank if rank else ''}{head}")
    lines.append(f"- font-family: \"{row.get('Font_Family', '')}\"")
    lines.append(f"- category: {row.get('Category', '')} | usage: {row.get('Usage', '')} "
                 f"| language: {row.get('language', '')}")
    lines.append(f"- mood: {row.get('Mood_Keywords', '')}")
    best = row.get("Best_For_CN") or row.get("Best_For") or ""
    lines.append(f"- best for: {best}")
    weights = (row.get("Weights") or "").strip()
    template = (row.get("CDN_URL_Template") or "").strip()
    if template and "{weight}" in template:
        lines.append(f"- weights: {weights} (multi-weight: one @font-face per weight + matching font-weight)")
        lines.append(f"- url template: {FONT_URL_PREFIX}{template} (replace {{weight}} with one of the weight "
                     f"names above, e.g. Regular/Bold)")
    else:
        lines.append(f"- weights: {weights or 'Regular'}")
        lines.append(f"- url: {font_url(row)}")
    if full:
        lines.append("- @font-face (paste as-is):")
        lines.append("```css")
        lines.append(font_face_snippet(row))
        lines.append("```")
    return "\n".join(lines)


class _StdoutParser(argparse.ArgumentParser):
    """Print usage errors on stdout.

    Callers habitually append `2>/dev/null | head -N`, which silently discards
    diagnostics written to stderr; a usage error then masquerades as "the script
    returned nothing" and wastes several rounds of trial and error. Usage errors
    must be visible.
    """

    def error(self, message):
        """Print the usage error on stdout with a hint, then exit 1."""
        self.print_usage(sys.stdout)
        print(f"{self.prog}: error: {message}")
        print()
        print("Mood keywords are the positional query (placed at the end), not --theme/--query:")
        print('  search_fonts.py "elegant refined dark" --usage heading --lang zh -n 5')
        sys.exit(1)


def main():
    """CLI entry: search the font library and print ranked candidates."""
    parser = _StdoutParser(
        description="Available font library search (the only legal font source)",
        epilog=(
            "Common mistakes (auto-corrected):\n"
            "  --usage display  → normalized to --usage heading\n"
            "  --theme/--mood/--style X → X is folded into the positional query\n"
            "  --lang en        → normalized to --lang latin\n"
            "\n"
            "Correct usage:\n"
            "  search_fonts.py \"elegant refined ceremonial\" --usage heading --lang zh\n"
            "  search_fonts.py \"minimal editorial\" --usage body --lang latin -n 5\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", nargs="?", default="",
                        help="mood/style/scenario keywords, Chinese and English may be mixed "
                             "(not --theme; put them at the end)")
    parser.add_argument("--usage", "-u",
                        help="body|heading. Synonyms such as display/title/headline are normalized to heading")
    parser.add_argument("--lang", "-l",
                        help="zh|tc|ja|latin. en/english/western normalize to latin; cn/chinese normalize to zh")
    parser.add_argument("--name", help="look up a single font by name (CN/EN/family)")
    parser.add_argument("--list", action="store_true", help="whole-library overview")
    parser.add_argument("-n", "--max-results", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="output as JSON (includes the url field)")

    # Common model mistake: --theme/--mood/--query/--style are meant to pass
    # mood keywords, but they aren't valid flags. Intercept them and fold their
    # values into the positional query so execution proceeds normally, instead
    # of erroring out and making the model retry repeatedly.
    argv = sys.argv[1:]
    extra_query_parts = []
    for fake_flag in ("--theme", "--mood", "--query", "--style", "--keyword", "--keywords"):
        while fake_flag in argv:
            idx = argv.index(fake_flag)
            if idx + 1 < len(argv) and not argv[idx + 1].startswith("-"):
                extra_query_parts.append(argv[idx + 1])
                argv = argv[:idx] + argv[idx + 2:]
            else:
                argv = argv[:idx] + argv[idx + 1:]

    args = parser.parse_args(argv)
    # Merge keywords extracted from misused flags into the positional query
    if extra_query_parts:
        args.query = ((args.query or "") + " " + " ".join(extra_query_parts)).strip()

    # Normalize arguments: map synonymous input to canonical values; give a
    # clear error plus a suggestion for unknown values.
    if args.usage:
        norm = USAGE_ALIASES.get(args.usage.lower())
        if not norm:
            print(f"Error: --usage '{args.usage}' is invalid. Only body or heading are accepted "
                  f"(synonyms like display/title/headline/text/copy are normalized automatically)", file=sys.stderr)
            return 1
        args.usage = norm
    if args.lang:
        norm = LANG_ALIASES.get(args.lang.lower())
        if not norm:
            print(f"Error: --lang '{args.lang}' is invalid. Only zh|tc|ja|latin are accepted "
                  f"(cn/chinese→zh, tw/traditional→tc, jp/japanese→ja, en/english/western→latin)", file=sys.stderr)
            return 1
        args.lang = norm

    if not DATA_CSV.exists():
        print(f"Error: font library not found: {DATA_CSV}", file=sys.stderr)
        return 1
    rows = load_fonts()

    if args.list:
        print(f"Font library: {len(rows)} fonts total | font_prefix={FONT_URL_PREFIX}")
        print("No | name | family | category | usage | language")
        for r in rows:
            print(
                f"{r.get('No', '')} | {r.get('Font_Name_CN', '')} ({r.get('Font_Name_EN', '')}) | "
                f"{r.get('Font_Family', '')} | {r.get('Category', '')} | {r.get('Usage', '')} | {r.get('language', '')}"
            )
        return 0

    if args.name:
        needle = args.name.strip().lower()
        hits = [
            r for r in rows
            if needle in (r.get("Font_Name_CN") or "").lower()
            or needle in (r.get("Font_Name_EN") or "").lower()
            or needle in (r.get("Font_Family") or "").lower()
        ]
        if not hits:
            print(f"Font '{args.name}' not found. The font library is the only legal source; "
                  f"switch to mood keywords and search instead.")
            return 1
        for r in hits:
            print(render(r))
            print()
        return 0

    if not args.query:
        parser.print_help()
        return 1

    candidates = [r for r in rows if passes_filters(r, args.usage, args.lang)]
    if not candidates:
        print("No candidates after filtering (check the --usage/--lang combination).")
        return 1

    docs = [" ".join(str(r.get(c, "")) for c in SEARCH_COLS) for r in candidates]
    bm25 = BM25()
    bm25.fit(docs)
    ranked = bm25.score(args.query)

    picked = [candidates[i] for i, s in ranked[: args.max_results] if s > 0]
    if not picked:
        # When keywords score zero, give a full fallback hint instead of
        # returning nothing. The index covers mood/style words (elegant /
        # refined / futuristic / playful…), not industry or product names
        # (e.g. "luxury bar" / "SaaS dashboard"), which always miss.
        print(f"Keyword '{args.query}' had no hits in the font library.")
        print()
        print("The library indexes mood/style words, not industry names/product names/'XX official site'.")
        print("Common mood keywords that will hit:")
        print("  Neutral/modern: modern / minimal / clean / geometric / neutral")
        print("  Elegant/classical: elegant / refined / classical / ceremonial / editorial")
        print("  Bold/industrial: bold / heavy / industrial / brutalist / condensed")
        print("  Playful/warm: playful / friendly / warm / rounded / handwritten")
        print("  Futuristic/tech: futuristic / techy / mono / digital")
        print()
        print("Suggested query rewrite (example):")
        print(f"  '{args.query}'")
        print(f"    → extract the visual mood, e.g. rewrite '奢华酒吧' as 'elegant refined dark'")
        print(f"    → or run --list to browse the whole library, or --name to look up a known font")
        return 1

    if args.json:
        out = []
        for r in picked:
            out.append({
                "name_cn": r.get("Font_Name_CN", ""),
                "name_en": r.get("Font_Name_EN", ""),
                "font_family": r.get("Font_Family", ""),
                "category": r.get("Category", ""),
                "usage": r.get("Usage", ""),
                "language": r.get("language", ""),
                "weights": r.get("Weights", ""),
                "url": font_url(r),
                "url_template": (
                    (FONT_URL_PREFIX + r["CDN_URL_Template"])
                    if (r.get("CDN_URL_Template") or "").strip() else ""
                ),
            })
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print(f"## Font candidates (query: {args.query}"
          + (f" | usage={args.usage}" if args.usage else "")
          + (f" | lang={args.lang}" if args.lang else "")
          + f") {len(picked)} fonts\n")
    for i, r in enumerate(picked, 1):
        print(render(r, rank=i, full=False))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
