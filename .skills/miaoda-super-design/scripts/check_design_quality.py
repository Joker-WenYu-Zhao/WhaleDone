#!/usr/bin/env python3
"""miaoda-super-design: deterministic design-draft quality check (format checker, pure stdlib).

Usage:
    python3 check_design_quality.py design/home-1.html [design/home-2.html ...]

Purpose: **only check deterministically judgeable format / contract / slop / readability hard floors**,
no aesthetic verdicts (taste questions like layout tension, font-size ratio, image density are left to
the references docs + differentiation engine to guide — no numeric thresholds forcing the model one way).

- Single file: runs all single-draft rules. Multiple files: additionally verifies structure / sig are
  pairwise distinct (first-round three-draft anti-reskinning).
- Violating any error rule or the multi-draft diversity gate → exit 1; the top-level `blocking` array lists
  the blocking reasons up front.
- Inline waiver (waivable rules only, for brand exceptions):
    <!-- miaoda-design-disable <rule-name>: <reason> -->
  Not waivable: tailwind version / self-contained / stamp / token block / structural integrity /
  section-id / font library / JSX self-closing / body min font size / spacing step / config integrity /
  config JS syntax.

stamp format (sig field required):
    <!-- miaoda-super-design | title: <style name ≤8 chars> | skeleton: <family> | sig: <unique signature> -->

Side effect: after printing the report, this script writes each verdict into
`manifest.json` in the drafts' own directory (`status` / `check_failed` only -- the
engineering side still owns designId, parent_ids, appType and the frontend signal).
Doing it in-process is deliberate: `check_draft_budget.py --check` reads the manifest,
so chaining the two in one shell command still sees this run's result.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

CLASS_ATTR = re.compile(r'(?<![\w-])class=["\']([^"\']*)["\']')
DISABLE = re.compile(r"<!--\s*miaoda-design-disable\s+([a-z0-9-]+)\s*:\s*(.+?)\s*-->")
# The `|` (ASCII) separator is the current format; `·` (U+00B7) is the legacy format, still
# accepted on read so historical drafts do not break.
STAMP = re.compile(
    r"<!--\s*miaoda-super-design"
    r"\s*\|\s*title:\s*([^|]+?)"
    r"\s*\|\s*skeleton:\s*([^|]+?)"
    r"\s*\|\s*sig:\s*(.+?)\s*-->"
)

APP_ROOT_RE = re.compile(r"^app-[\w-]+$")


def _walk_up_for_app(start):
    """Walk up from `start` to the first `app-<id>` directory; None if there is none."""
    probe = os.path.abspath(start)
    while True:
        if APP_ROOT_RE.match(os.path.basename(probe)):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent


def find_app_root():
    """Locate the current app root `app-<id>`: try CWD's ancestors, then this script's.

    CWD may be the app's parent (e.g. /workspace); the app-<id> dir would then be
    a child and unreachable by walking up. The script lives under
    <app-root>/.skills/miaoda-super-design/scripts/, so __file__'s ancestry always
    contains app-<id> — a more reliable anchor. Fall back to CWD for local debugging.
    """
    hit = _walk_up_for_app(os.getcwd())
    if hit:
        return hit
    hit = _walk_up_for_app(os.path.dirname(os.path.abspath(__file__)))
    if hit:
        return hit
    return os.path.abspath(os.getcwd())


def resolve_input_path(arg):
    """Keep absolute paths as-is; resolve relative paths against the app root."""
    if os.path.isabs(arg):
        return os.path.abspath(arg)
    return os.path.join(find_app_root(), arg)


def class_text(html):
    """Concatenate every class attribute value in the document into one string."""
    return " ".join(CLASS_ATTR.findall(html))


# ---------- checkers: each returns a list of problem descriptions ----------

def chk_tailwind_version(html):
    """Tailwind must be the v3 CDN build pinned to a fixed version."""
    out = []
    if "@tailwindcss/browser" in re.sub(r"<!--.*?-->", "", html, flags=re.S):
        out.append("Using Tailwind v4 @tailwindcss/browser (hard rule: v3 only)")
    m = re.search(r'(?<![\w-])src=["\']https://cdn\.tailwindcss\.com([^"\']*)["\']', html)
    if not m:
        out.append("Missing https://cdn.tailwindcss.com/3.4.16 script import")
    elif not re.match(r"^/3\.", m.group(1)):
        out.append(
            f"Tailwind CDN not pinned to a fixed v3 version"
            f" (current: '{m.group(1) or 'no version'}', should be /3.4.16)"
        )
    return out


def chk_local_refs(html):
    """Local images must use the full absolute path `/workspace/<app-id>/tasks/design/assets/<name>`;
    no sideloaded local css/js.

    Remote CDNs (https://...) are unrestricted -- motion libraries (Swiper / anime.js / lottie
    etc.) may be pulled from a version-pinned CDN. This rule only catches local path forms.

    The preview container resolves local files by full absolute path: neither the relative
    `assets/x.jpg` nor the site-root `/tasks/design/assets/x.jpg` carries app-locating
    information, so the image breaks.

    Strip <script> blocks before scanning (same treatment as chk_section_ids): the
    `` `<img src="${p.image}">` `` inside a list-rendering script is a template-literal
    interpolation evaluated at runtime into a real URL, not a local path reference in the HTML.
    Without stripping, it gets flagged as an illegal local reference -- and to silence the error
    the model rewrites the template literal into single-quote concatenation
    (`src="' + p.image + '"`), which, inside a backtick string, emits the concatenation
    operators literally into the HTML and guarantees a broken image. The false positive directly
    induces a real failure, so stripping is mandatory.
    """
    out = []
    html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
    full = re.compile(r"^/workspace/app-[\w-]+/tasks/design/assets/[\w.-]+$")
    site_root = re.compile(r"^/tasks/design/assets/([\w.-]+)$")
    relative = re.compile(r"^assets/([\w.-]+)$")
    for attr, url in re.findall(r'(?<![\w-])(src|href)=["\']([^"\']+)["\']', html):
        if url.startswith(("http://", "https://", "#", "data:", "mailto:", "tel:", "javascript:")):
            continue
        if attr == "src" and full.match(url):
            continue  # the only legal form for local assets
        m = site_root.match(url) or relative.match(url)
        if attr == "src" and m:
            out.append(
                f'Local reference src="{url}" is missing the `/workspace/<app-id>` prefix'
                f' (the image will break in preview) — change it to'
                f' src="/workspace/<current app-id>/tasks/design/assets/{m.group(1)}"'
            )
            continue
        out.append(
            f'Local reference {attr}="{url}" is illegal'
            ' (local images may only use src="/workspace/<app-id>/tasks/design/assets/<name>";'
            ' no sideloaded local css/js)'
        )
    return out


def chk_stamp(html):
    """The stamp comment must be present, parseable, and have title/sig both filled in."""
    m = STAMP.search(html)
    if not m:
        if "miaoda-super-design" in html:
            return [
                "stamp parse failed: a `|` character appears inside the title / skeleton field —"
                " `|` is the stamp's field separator and cannot appear inside a field value."
                " title should only contain a condensed style term (no brand name, no connectors)"
            ]
        return [
            "Missing stamp comment: <!-- miaoda-super-design | title: <title>"
            " | skeleton: <name> | sig: <draft-unique signature> -->"
        ]
    title = m.group(1).strip()
    sig = m.group(3).strip()
    out = []
    if not title or title.startswith("<"):
        out.append("stamp's title is not filled in: ≤8 chars condensing the design style,"
                    " the engineering scan registers the html based on this")
    else:
        # Count characters after removing spaces; connectors banned (models love pairing
        # "brand | style" which exceeds the limit)
        SEPARATORS = re.compile(r"[·\-—|/]")
        if SEPARATORS.search(title):
            out.append(
                f"stamp title '{title}' contains a connector (·—|/) — title should only contain"
                " a condensed style term, do not pair it with a brand name"
            )
        elif len(title.replace(" ", "")) > 8:
            out.append(f"stamp's title '{title}' exceeds 8 chars (condensed design style, ≤8 chars)")
    if not sig or sig.startswith("<"):
        out.append(
            "stamp's sig is not filled in: write a signature unique to this draft"
            " (an elevated craft detail grown from the PRD's business context, not in the template),"
            " and it must differ across drafts"
        )
    elif len(sig.replace(" ", "")) < 6:
        out.append(
            f"stamp's sig '{sig}' is too short (<6 chars): it must clearly convey what makes this draft's"
            " visual signature unique, not restate the style name"
        )
    return out


def chk_tokens_block(html):
    """DESIGN-TOKENS block must exist (derived from assets/base.html)."""
    return [] if "DESIGN-TOKENS:BEGIN" in html else ["Missing DESIGN-TOKENS block (derived from assets/base.html)"]


def chk_html_integrity(html):
    """HTML structural integrity: deterministic interception of common truncation / leftover
    patterns from huge str_replace operations.

    When the model does a 12k+ character str_replace over a whole block, new_str can be cut off
    by the output limit, producing a draft with missing closing tags or a mutilated script body.
    Browsers raise no error on such drafts and the damage is hard to spot by eye.

    Checks:
      1. Missing key closers: at least one each of </body> / </html>
      2. <script> open and close counts must match
      3. The <body> opening tag must exist exactly once (missing or duplicated both invalid)
      4. No leftover content after </html> (see below)
      5. </head> / </body> must each appear exactly once, and <style> must be balanced.
         A whole-block str_replace that carries head's tail along drops a fragment
         ("} /* ===== CUSTOM-TOKENS:END ===== */ ... </style></head>") into the middle of
         the body. Every tail check above still passes, yet the browser renders the orphaned
         CSS as a visible text node.
      6. No token-block markers inside <body> (same failure as above, caught directly)
    """
    out = []
    body_close_tags = re.findall(r"</body\s*>", html, re.I)
    if len(body_close_tags) == 0:
        out.append("Missing </body> closing tag — the file may be truncated;"
                    " trailing body content / scripts may be lost")
    elif len(body_close_tags) > 1:
        out.append(
            f"</body> closing tag appears {len(body_close_tags)} times — a whole-block str_replace"
            " duplicated the document tail; delete the extra one"
        )
    m_html_close = re.search(r"</html\s*>", html, re.I)
    if not m_html_close:
        out.append("Missing </html> closing tag — the file may be truncated")

    head_close_tags = re.findall(r"</head\s*>", html, re.I)
    if len(head_close_tags) > 1:
        out.append(
            f"</head> closing tag appears {len(head_close_tags)} times — a whole-block str_replace"
            " pasted head's tail into the body; everything around the stray </head> renders as"
            " visible text. Keep exactly one </head>"
        )

    style_open = len(re.findall(r"<style(?:\s[^>]*)?>", html, re.I))
    style_close = len(re.findall(r"</style\s*>", html, re.I))
    if style_open != style_close:
        out.append(
            f"<style> open/close count mismatch ({style_open} open / {style_close} close) — the CSS"
            " before an orphaned </style> is not inside a style element, so the browser renders it"
            " as literal text on the page"
        )

    body_open_tags = re.findall(r"<body(?:\s[^>]*)?>", html, re.I)
    if len(body_open_tags) == 0:
        out.append(
            "Missing <body> opening tag — likely dropped by a whole-block str_replace;"
            " its bg-background/text-foreground classes are lost, text renders default black"
        )
    elif len(body_open_tags) > 1:
        out.append(
            f"<body> opening tag appears {len(body_open_tags)} times — invalid HTML, browser behavior is not"
            " guaranteed to be consistent; delete the extra one"
        )

    script_open = len(re.findall(r"<script(?:\s[^>]*)?>", html, re.I))
    script_close = len(re.findall(r"</script\s*>", html, re.I))
    if script_open != script_close:
        out.append(
            f"<script> open/close count mismatch ({script_open} open / {script_close} close) —"
            " a common truncation symptom of a whole-block str_replace; the script body may be incomplete"
        )

    # Take the last </html>, not the first: JS strings / template literals occasionally contain
    # the substring "</html>", and slicing trailing content from the first match would flag the
    # legitimate ending after the real closing tag as leftover. Using the last match handles
    # "a fake </html> literal appears once in the body but the document really closes only once";
    # for a genuine duplicate close (both in tag form) there is nothing after the last one either,
    # so the first case is still not missed.
    all_html_close = list(re.finditer(r"</html\s*>", html, re.I))
    if all_html_close:
        last_close = all_html_close[-1]
        trailing = html[last_close.end():]
        trailing_stripped = re.sub(r"<!--.*?-->", "", trailing, flags=re.S).strip()
        if trailing_stripped:
            out.append(
                "Trailing content after </html> — the browser re-parses it into <body> and it "
                "executes; leftover :root remnants silently override earlier tokens (page looks "
                "washed-out). Delete everything after </html>"
            )

    # CSS-block markers must live inside the head's <style>. Strip every style/script element
    # first, so a marker still enclosed in one does not count; whatever is left sits directly in
    # the markup and the browser paints it as text. MOTION-SCRIPT is excluded on purpose -- it
    # legitimately lives in a body <script>.
    stray_markers = sorted({
        m.group(1) for m in re.finditer(
            r"=====\s*(DESIGN-TOKENS|CUSTOM-TOKENS|SIGNATURE-CSS|KEYFRAMES|ANIMATIONS)"
            r":(?:BEGIN|END)\s*=====",
            _html_only(html),
        )
    })
    if stray_markers:
        out.append(
            f"Token-block marker(s) {', '.join(stray_markers)} sit outside <style>/<script> — a"
            " whole-block str_replace pasted a head fragment into the markup, and the browser"
            " renders those comments plus the CSS around them as visible text. Delete the"
            " misplaced fragment"
        )
    return out


SECTION_ID_RE = re.compile(r'(?<![\w-])id=["\']([^"\']+)["\']')


def _html_only(html):
    """Strip <script>/<style> so their contents (CSS url(...) data-URIs, JS strings)
    don't collide with HTML attribute regexes.
    """
    out = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
    out = re.sub(r"<style\b.*?</style>", "", out, flags=re.S | re.I)
    return out


def chk_section_ids(html):
    """Verify <section id=...> presence and uniqueness of every id= on the page.

    The id doubles as the in-page anchor target for nav <a href="#X"> — a plain \\b
    won't work here (the hyphen ends a word), so a negative lookbehind for [\\w-]
    is used to keep `data-*-id=` / `aria-labelledby=` out.
    """
    html_only = _html_only(html)
    ids = SECTION_ID_RE.findall(html_only)
    out = []
    if not re.search(r"<section\b[^>]*(?<![\w-])id=", html_only, re.I):
        out.append("No <section id=...> at all (each semantic section needs a unique id=,"
                   " which doubles as the in-page anchor target)")
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        out.append(f"Duplicate id: {sorted(dup)}")
    return out


def chk_color_fn_double_wrap(html):
    """A custom token already holding a complete color must not be re-wrapped.

    Two legal patterns exist and are easy to mix up:
      A) base token holds a bare triplet   --muted: 220 9% 64%    -> use hsl(var(--muted))
      B) custom token holds a full color   --sig-accent: #ba871d  -> use var(--sig-accent)
    Mixing B's definition with A's usage yields hsl(hsl(...)) / rgb(#...), which is
    invalid CSS: the declaration is dropped and the element falls back (transparent
    background, inherited text color).

    Only variables whose own definition starts with a color function or # are flagged,
    so pattern A keeps passing untouched.
    """
    full_color_vars = set()
    for block in re.findall(r"CUSTOM-TOKENS:BEGIN(.*?)CUSTOM-TOKENS:END", html, re.S):
        for name, value in re.findall(r"--([\w-]+)\s*:\s*([^;}]+)", block):
            if re.match(r"\s*(?:#|hsla?\(|rgba?\(|oklch\(|color-mix\()", value):
                full_color_vars.add(name)
    if not full_color_vars:
        return []
    out = []
    for fn, name in re.findall(r"(hsla?|rgba?|oklch)\(\s*var\(\s*--([\w-]+)\s*\)", html):
        if name in full_color_vars:
            out.append(f"--{name} already holds a complete color value, but it is wrapped again"
                       f" as {fn}(var(--{name})) — this expands to {fn}({fn}(…)) and is invalid CSS"
                       f" (the element falls back to transparent/inherited)."
                       f" Use var(--{name}) directly")
    return sorted(set(out))


def chk_inline_hex(html):
    """No arbitrary hex value in class or inline style — colors must use semantic tokens."""
    out = []
    if re.search(r"\[#[0-9a-fA-F]{3,8}\]", class_text(html)):
        out.append("Arbitrary hex value in class (e.g. bg-[#123456]) — colors must use semantic token classes only")
    for style in re.findall(r'(?<![\w-])style=["\']([^"\']*)["\']', html):
        if re.search(r"#[0-9a-fA-F]{3,8}\b", style) or re.search(r"rgba?\(", style):
            out.append(f"Inline style contains a direct color value: '{style[:60]}…'")
    return out


def chk_direct_palette(html):
    """No Tailwind direct-palette utility classes — colors must go through semantic tokens."""
    pal = r"(?:bg|text|border|from|to|via|ring|fill|stroke|decoration|divide|outline|shadow|accent|caret)"
    color = (r"(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald"
             r"|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)")
    hits = sorted(set(re.findall(pal + "-" + color + r"-\d{2,3}", class_text(html))))
    return [f"Direct palette classes (forbidden, use semantic tokens): {hits[:8]}"] if hits else []


def chk_gradient_text(html):
    """Flag gradient text (bg-clip-text + text-transparent) — a hard slop rule."""
    c = class_text(html)
    if "bg-clip-text" in c and "text-transparent" in c:
        return ["Gradient text (bg-clip-text + text-transparent) = slop hard rule"]
    return []


def chk_purple_gradient(html):
    """Flag the purple/blue-family gradient combo — a universal AI slop formula."""
    c = class_text(html)
    if (re.search(r"from-(?:purple|violet|indigo|fuchsia)-", c)
            and re.search(r"to-(?:blue|purple|violet|indigo|pink|fuchsia)-", c)):
        return ["Purple/blue-family gradient combo = AI slop universal formula"]
    return []


def chk_lorem(html):
    """No lorem ipsum placeholder text."""
    if re.search(r"lorem\s+ipsum", html, re.I):
        return ["lorem ipsum present — use an honest placeholder or real content"]
    return []


def chk_base64_img(html):
    """No large base64-inlined images — use an https URL or a local assets path."""
    for m in re.finditer(r'(?<![\w-])src=["\'](data:image/[^"\']+)["\']', html):
        if len(m.group(1)) > 2048:
            return ["Large base64-inlined image (use an https URL or a full absolute path"
                    " /workspace/<app-id>/tasks/design/assets/<name> for images)"]
    return []


def chk_emoji_icons(html):
    """Flag emoji used as icons in the body (slop, unless brand/kids context)."""
    body = html.split("</head>", 1)[-1]
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    hits = re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", body)
    if hits:
        return [f"{len(hits)} emoji found in body (emoji as icons is slop, unless brand/kids context)"]
    return []


FONT_LIB_PREFIX = "https://resource-static.bj.bcebos.com/fonts-skill/"
# Trusted font domains: bj.bcebos.com (fonts.csv default) + cdn.bcebos.com (legacy, in some
# theme.xlsx specs). Trust the domain, not the filename — the two sources aren't cross-validated.
TRUSTED_FONT_HOSTS = (
    "resource-static.bj.bcebos.com",
    "resource-static.cdn.bcebos.com",
)
FONT_CDN_HOSTS = (
    "fonts.googleapis.com", "fonts.gstatic.com", "fonts.bunny.net",
    "use.typekit.net", "fonts.loli.net",
)


def chk_font_library(html):
    """Fonts may only come from trusted domains (TRUSTED_FONT_HOSTS); filenames are not matched
    against fonts.csv one by one.

    fonts.csv and theme.xlsx are independently maintained, so the same typeface can differ in
    filename/extension across them. A filename mismatch is therefore not an "off-library font";
    only a font on neither trusted domain (model-invented or a real third-party CDN) is blocked.
    """
    out = []
    for host in FONT_CDN_HOSTS:
        if host in html:
            out.append(
                f"References a non-approved font CDN {host} (fonts must come from the data/fonts.csv"
                " available font library; search via scripts/search_fonts.py)"
            )
    for m in re.finditer(r"@font-face[^{}]*\{[^}]*?url\(\s*['\"]?([^'\")\s]+)", html, re.S):
        url = m.group(1)
        if not url.startswith(("http://", "https://")):
            continue
        host_m = re.match(r"https?://([^/]+)/", url)
        host = host_m.group(1) if host_m else ""
        if host not in TRUSTED_FONT_HOSTS:
            out.append(
                f"@font-face references domain '{host}' which is not a trusted font domain"
                f" (URL: {url[:80]}) — use search_fonts.py to find the correct address"
            )
    return out



GENERIC_FONT_FAMILIES = {
    "sans-serif", "serif", "monospace", "cursive", "fantasy", "system-ui",
    "ui-sans-serif", "ui-serif", "ui-monospace", "ui-rounded",
    "inherit", "initial", "unset", "revert", "revert-layer",
}


def chk_font_face_required(html):
    """Every font-family used must have an @font-face registered; otherwise it falls back silently."""
    stripped = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
    registered = set()
    for block in re.findall(r"@font-face\s*\{([^}]*)\}", stripped, re.S):
        m = re.search(r"font-family:\s*(['\"]?)([^;'\"]+)\1", block)
        if m:
            registered.add(m.group(2).strip())
    if not registered:
        return [
            "No @font-face registered — every font-family falls back to system fonts silently. "
            "Register the fonts this draft uses"
        ]
    missing = set()
    for stack in re.findall(r"font-family:\s*([^;}]+)", stripped):
        first = stack.split(",", 1)[0].strip().strip("'\"")
        if not first or first.startswith("var(") or first.lower() in GENERIC_FONT_FAMILIES:
            continue
        if first not in registered:
            missing.add(first)
    if not missing:
        return []
    return [
        f"font-family used but not registered: {sorted(missing)}. The browser silently falls back "
        "to system fonts. Add an @font-face rule for each, or drop the unused font-family"
    ]


def chk_tiny_text(html):
    """Flag any arbitrary font size below 12px — a hard readability floor."""
    hits = sorted(set(re.findall(r"text-\[(\d+)px\]", class_text(html))))
    bad = [h for h in hits if int(h) < 12]
    if not bad:
        return []
    return [f"Font size <12px: text-[{'/'.join(bad)}px]"
            " (readability hard floor, not waivable for any style)"]


# Integer steps of Tailwind v3's default spacing scale (the full scale also has px / 0.5 / 1.5 /
# 2.5 / 3.5; fractional and px steps are naturally excluded by the regex, so only integers are
# checked). Steps like 13/15/17/18/19/22/26... **do not exist**: the scale jumps from 12 to 14,
# and after 16 it increments by 4.
TW_SPACING_STEPS = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 20, 24, 28, 32, 36, 40,
    44, 48, 52, 56, 60, 64, 72, 80, 96,
}
# Only utility prefixes driven by the spacing scale; longer prefixes come first so `gap-x-13` is
# not truncated to `gap` and misjudged. Deliberately excludes families with their own separate
# scales such as grid-cols / z / order / leading / duration.
SPACING_PREFIXES = sorted(
    ["gap-x", "gap-y", "space-x", "space-y", "inset-x", "inset-y",
     "translate-x", "translate-y", "gap", "inset", "size",
     "px", "py", "pt", "pr", "pb", "pl", "ps", "pe", "p",
     "mx", "my", "mt", "mr", "mb", "ml", "ms", "me", "m",
     "top", "right", "bottom", "left", "start", "end", "w", "h"],
    key=len, reverse=True,
)
SPACING_CLASS = re.compile(
    r"(?:^|[\s:])-?(" + "|".join(re.escape(p) for p in SPACING_PREFIXES) + r")-(\d+)(?=$|\s)"
)
# Object names under theme.extend that may declare custom steps; on a hit, their integer keys
# join the whitelist.
SPACING_THEME_KEYS = (
    "spacing", "width", "height", "minHeight", "maxHeight", "minWidth", "maxWidth",
    "padding", "margin", "gap", "inset", "space", "size", "translate",
)
# Only accept keys whose value carries a length unit, so keyframes entries like '0%': {...} are
# not mistaken for scale declarations.
SPACING_THEME_STEP = re.compile(
    r"""(?:^|[{,\s])(['"]?)(\d+)\1\s*:\s*['"]?[^,}]*?(?:rem|px|em|%|vh|vw|ch|ex|calc)"""
)


def _balanced_body(text, brace_pos):
    """Return the full object body (nesting included) up to the `{` at text[brace_pos]'s match.

    `\\{[^{}]*\\}` cannot be used to grab the theme object -- `spacing: { ... }` may nest, and an
    adjacent `keyframes: { 'x': { ... } }` makes a non-nesting regex slip and capture a different
    object body.
    """
    depth = 0
    for i in range(brace_pos, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace_pos + 1:i]
    return ""


def _declared_spacing_steps(html):
    """Collect integer spacing steps declared in the page's own tailwind.config theme extensions."""
    steps = set()
    for key in SPACING_THEME_KEYS:
        for m in re.finditer(r"\b" + key + r"\s*:\s*\{", html):
            for km in SPACING_THEME_STEP.finditer(_balanced_body(html, m.end() - 1)):
                steps.add(int(km.group(2)))
    return steps


def chk_spacing_scale(html):
    """Catch steps that do not exist on the Tailwind spacing scale (`h-13` / `mt-15` / `gap-17`...).

    Such classes compile to no CSS at all: Tailwind only generates steps that are on the scale,
    so `h-13` silently does nothing and the element falls back to a content-driven height. No
    error, no trace -- absolutely positioned children inside it (icon buttons and the like) end up
    misaligned. The symptom is a control with off proportions that just looks undesigned, and it
    is very hard to trace by eye back to a class that does not exist.

    The whitelist comes from the page's own `tailwind.config`: an integer key declared in
    `spacing`/`height`/`gap` etc. (with a length-unit value) is allowed through -- wanting a step
    of 13 is legitimate, provided it is declared first. Arbitrary values (`h-[52px]`), fractional
    steps (`w-1/2`), and keyword steps (`h-full`/`h-screen`) do not match this rule's shape and
    are unaffected.
    """
    allowed = TW_SPACING_STEPS | _declared_spacing_steps(html)
    bad = sorted({
        f"{prefix}-{num}"
        for prefix, num in SPACING_CLASS.findall(class_text(html))
        if int(num) not in allowed
    })
    if not bad:
        return []
    return [
        f"Tailwind spacing step does not exist: {bad[:8]} — compiles to no CSS, so the size "
        "silently fails and absolutely-positioned children misalign. Use an adjacent valid step, "
        "an arbitrary value (`h-[3.25rem]`), or declare it in tailwind.config spacing first"
    ]


KEYFRAMES_BLOCK = re.compile(r"KEYFRAMES:BEGIN(.*?)KEYFRAMES:END", re.S)
KEYFRAMES_NAME = re.compile(r"""['"]([\w-]+)['"]\s*:\s*\{""")
NATIVE_KEYFRAMES_NAME = re.compile(r"@keyframes\s+([\w-]+)")
ANIMATION_PROP_REF = re.compile(r"animation(?:-name)?\s*:\s*([\w-]+)")

# `'name': {` / `name: {` heading a keyframe definition inside the KEYFRAMES block
KEYFRAMES_ENTRY = re.compile(r"""['"]?([\w-]+)['"]?\s*:\s*\{""")
# A CSS property assignment inside a keyframe step: `opacity: '0'` / `clipPath: "inset(...)"`.
# Percentage step keys (`'0%': {`) do not match -- their value is `{`, not a quote.
KEYFRAMES_STEP_PROP = re.compile(r"""([A-Za-z][\w-]*)\s*:\s*['"]""")
# Elements wired to the CSS entrance channel
INTERSECT_ANIMATE = re.compile(r"intersect:animate-([\w-]+)")
# The observer library that flips `no-intersect` off; without it every start state is permanent
INTERSECT_OBSERVER_REF = re.compile(r"tailwindcss-intersect")
# `intersect` is a variant (`&:not([no-intersect])`), not a class -- adding it triggers nothing
INTERSECT_CLASS_ADD = re.compile(
    r"""classList\s*\.\s*add\s*\(\s*['"]intersect['"]"""
)
# Opacity start states that hide the element until the animation raises opacity again
OPACITY_START = re.compile(r"(?<![\w-])opacity-(0|5|10|20)(?![\w-])")


def _keyframe_animated_props(html):
    """Map each keyframe name in the KEYFRAMES block to the CSS properties it animates."""
    block = KEYFRAMES_BLOCK.search(html)
    if not block:
        return {}
    body = block.group(1)
    out = {}
    for m in KEYFRAMES_ENTRY.finditer(body):
        name = m.group(1)
        if name.endswith("%"):
            continue
        steps = _balanced_body(body, m.end() - 1)
        props = {p.lower() for p in KEYFRAMES_STEP_PROP.findall(steps)}
        if props:
            out[name] = props
    return out


def chk_intersect_start_state(html):
    """The CSS entrance channel only works when the start state and the keyframe touch the same
    property, and when the observer that clears `no-intersect` is actually loaded.

    Three silent runtime failures, all of which leave every other rule green:

    1. Start state on a property the keyframe never animates. `opacity-0` plus a keyframe that
       only moves `clipPath`/`transform` means opacity stays 0 for good -- the element (and its
       whole subtree) never becomes visible. Observed symptom: a draft that renders blank because
       the section wrapping the page's body content carried `opacity-0`.
    2. `intersect:` classes with no `tailwindcss-intersect` script. Nothing ever removes the
       `no-intersect` attribute, so every start state is permanent.
    3. `classList.add('intersect')`. `intersect` is a Tailwind variant compiled to
       `&:not([no-intersect])`, not a class; adding it changes nothing. This is the shape a
       hand-rolled IntersectionObserver replacement takes when it replaces the real library.
    """
    out = []
    used = sorted(set(INTERSECT_ANIMATE.findall(html)))
    if used and not INTERSECT_OBSERVER_REF.search(html):
        out.append(
            f"intersect:animate-* is used ({', '.join(used[:4])}) but the tailwindcss-intersect "
            "script is missing — nothing ever clears the `no-intersect` attribute, so each start "
            "state (opacity-0 and friends) becomes permanent and the elements never appear. "
            "Restore the observer script from assets/base.html"
        )
    if INTERSECT_CLASS_ADD.search(html):
        out.append(
            "classList.add('intersect') does nothing — `intersect` is a Tailwind variant compiled "
            "to `&:not([no-intersect])`, not a class. Use the tailwindcss-intersect script from "
            "assets/base.html instead of a hand-rolled observer"
        )

    animated = _keyframe_animated_props(html)
    mismatched = []
    for m in re.finditer(r'class="([^"]*)"', html):
        cls = m.group(1)
        hit = INTERSECT_ANIMATE.search(cls)
        if not hit or not OPACITY_START.search(cls):
            continue
        name = hit.group(1)
        props = animated.get(name)
        if props is not None and "opacity" not in props:
            mismatched.append((name, sorted(props)))
    if mismatched:
        detail = "; ".join(
            f"animate-{n} only animates {', '.join(p)}" for n, p in mismatched[:3]
        )
        more = "" if len(mismatched) <= 3 else f" (+{len(mismatched) - 3} more)"
        out.append(
            f"Start state `opacity-0` paired with a keyframe that never animates opacity — "
            f"{detail}{more}. Opacity stays 0 after the animation finishes, so the element and "
            "everything inside it stay invisible for good. Take the start state from the "
            "keyframe's own 0% properties, or add opacity to the keyframe"
        )
    return out


def chk_keyframes_wired(html):
    """The KEYFRAMES block is a Tailwind config object (feeding `animate-<name>` utility classes),

    not a native CSS `@keyframes` rule; the two look similar but are not interchangeable. If a
    hand-written CSS rule uses `animation: <name> ...` to reference a name defined in the
    KEYFRAMES block and the page has no native `@keyframes` rule of the same name, the browser
    silently ignores the animation -- no error, and the element stays in its initial state forever
    (typical symptom: entrance-animated elements never appear, the page looks half-loaded). This
    is a silent runtime failure; without this check it only surfaces via a manual screenshot.
    """
    m = KEYFRAMES_BLOCK.search(html)
    if not m:
        return []
    kf_names = set(KEYFRAMES_NAME.findall(m.group(1)))
    if not kf_names:
        return []
    native = set(NATIVE_KEYFRAMES_NAME.findall(html))
    broken = sorted(
        name for name in set(ANIMATION_PROP_REF.findall(html))
        if name in kf_names and name not in native
    )
    if not broken:
        return []
    names = ", ".join(broken)
    return [
        f"CSS `animation:` references {names} from the KEYFRAMES block, but that name only exists "
        "in the Tailwind config, not as a native @keyframes rule — the browser silently ignores it "
        "and the element stays in its initial state. Trigger it via a class instead: "
        "`intersect:animate-<name> intersect-once`"
    ]


TAILWIND_CONFIG_ASSIGN = re.compile(r"tailwind\.config\s*=\s*\{")
_NODE = shutil.which("node")

# Innermost array literals: bare strings are legal inside arrays
# (fontFamily: ['Jost', 'sans-serif']), so they must be stripped wholesale before scanning,
# otherwise a `, 'x' ,` between elements is misread as a missing key.
ARRAY_LITERAL = re.compile(r"\[[^\[\]]*\]", re.S)

# A bare string in object position: `{ 'x', y: 1 }` / `, 'x' ,` -- the residue of a deleted key.
# A legitimate string value is always preceded by `key:`, so the colon is the decisive anchor.
# Here we require `{` or `,` immediately before and `,` or `}` immediately after; normal code
# never lands in this shape.
ORPHAN_STRING_VALUE = re.compile(r"""[{,]\s*(['"])((?:\\.|(?!\1).){1,120})\1\s*(?=[,}])""", re.S)


def chk_config_integrity(html):
    """Regex fallback for `tailwind.config` validity, used only when node is unavailable.

    config-js-syntax parses the block with a real JS parser and is a strict superset of this rule,
    so running both would report one defect twice. This one covers the single most common broken
    shape without any external dependency: `sed 's/lg://g'` used to bulk-strip breakpoint prefixes
    also deletes the key in `borderRadius: { lg: '…' }`, leaving `{ '…', md: … }` -- a bare string
    in object position.

    Either way the consequence is the same: one syntax error makes the whole config throw, so
    colors / keyframes / fontFamily / borderRadius never register, `bg-primary` and `animate-*`
    silently emit nothing, and the page collapses to browser defaults while the HTML stays intact
    and every other rule stays green -- the hardest class of false pass to diagnose.

    Array literals are stripped first, since bare strings inside arrays are legal
    (fontFamily: ['Jost', 'sans-serif']).
    """
    if _NODE:
        return []  # config-js-syntax covers this and more
    m = TAILWIND_CONFIG_ASSIGN.search(html)
    if not m:
        return []
    body = _balanced_body(html, m.end() - 1)
    if not body:
        return ["tailwind.config = {...} has unbalanced braces — the config throws at runtime and no "
                "custom color / keyframe / font / radius registers."]
    prev = None
    while prev != body:
        prev, body = body, ARRAY_LITERAL.sub(" ", body)
    orphans = [v[:40] for _, v in ORPHAN_STRING_VALUE.findall(body)]
    if not orphans:
        return []
    sample = ", ".join(f"'{s}'" for s in orphans[:4])
    more = "" if len(orphans) <= 4 else f" +{len(orphans) - 4} more"
    return [
        f"tailwind.config has {len(orphans)} bare string(s) with no key ({sample}{more}) — "
        "JS syntax error, all custom classes emit nothing. Restore the missing object keys."
    ]


def chk_config_js_syntax(html):
    """Parse the `tailwind.config = {...}` block with `node --check` (syntax only, never executes).

    Superset of config-integrity: catches every JS syntax error, not just the one regex-detectable
    shape. The failure mode that motivated it: a keyframe CSS property whose name contains a hyphen
    left unquoted (`stroke-dashoffset: '24'`) parses as the subtraction `stroke - dashoffset`, so the
    whole assignment throws and no custom color / font / keyframe / radius ever registers -- the page
    silently falls back to browser defaults while every other rule stays green.

    Regex can only enumerate the broken shapes someone thought of; a real parser needs no such list.
    Skipped when node is unavailable (config-integrity still covers the common shape). `--check` only
    parses, so nothing in the draft can run.
    """
    if not _NODE:
        return []
    m = TAILWIND_CONFIG_ASSIGN.search(html)
    if not m:
        return []
    body = _balanced_body(html, m.end() - 1)
    if not body:
        return []  # unbalanced braces: config-integrity already reports this
    path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(f"tailwind.config = {{{body}}};\n")
            path = f.name
        proc = subprocess.run([_NODE, "--check", path], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []  # node broke or timed out: stay silent rather than block on tooling
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
    if proc.returncode == 0:
        return []
    lines = [ln.strip() for ln in (proc.stderr or "").splitlines() if ln.strip()]
    detail = next((ln for ln in lines if "Error:" in ln), lines[-1] if lines else "unknown")
    return [
        f"tailwind.config JS syntax error — {detail}. All custom classes emit nothing. "
        "Common cause: unquoted hyphenated key (`'stroke-dashoffset'` needs quotes)."
    ]


MOTION_BLOCK = re.compile(
    r"MOTION-SCRIPT:BEGIN\s*={3,}\s*\*/(.*?)/\*\s*={3,}\s*MOTION-SCRIPT:END", re.S
)
# Top-level `const {animate} = window` runs synchronously, before the deferred module has
# assigned those functions -- it captures undefined. Only a destructure that sits inside the
# motion:ready callback (or plain `window.animate(...)`) sees the real values.
MOTION_TOPLEVEL_DESTRUCTURE = re.compile(
    r"^[ \t]*(?:const|let|var)\s*\{[^}]*\}\s*=\s*window\b", re.M
)


def chk_motion_window_timing(html):
    """Catch `const {animate,...} = window` placed outside the motion:ready callback.

    motion's functions reach `window` only after the deferred `<script type="module">` finishes
    importing. A destructure at the top of the MOTION-SCRIPT block therefore binds undefined, and
    every later call throws inside the event handler -- silently, since the throw happens in a
    listener. Symptom: every element that starts at `opacity-0` waiting for an entrance animation
    stays invisible, so the page reads as blank while the HTML and CSS are both fine.
    """
    m = MOTION_BLOCK.search(html)
    if not m:
        return []
    body = m.group(1)
    # Text before the first motion:ready listener is the block's synchronous top level.
    listener = re.search(r"addEventListener\s*\(\s*['\"]motion:ready['\"]", body)
    top_level = body[: listener.start()] if listener else body
    if not MOTION_TOPLEVEL_DESTRUCTURE.search(top_level):
        return []
    return [
        "MOTION-SCRIPT destructures motion helpers from `window` at the block's top level, before "
        "the deferred module assigns them — they bind undefined, animate() throws, and opacity-0 "
        "elements stay invisible. Move the destructure inside the motion:ready callback."
    ]


NONVOID_SELF_CLOSING = re.compile(
    r"<(span|div|p|a|button|section|article|main|header|footer|nav|ul|ol|li"
    r"|h[1-6]|em|strong|i|b|u|s|label|form|select|textarea|option|table|thead"
    r"|tbody|tfoot|tr|td|th|figure|figcaption|aside|blockquote|dl|dt|dd|small"
    r"|sup|sub|code|pre|video|audio|canvas|details|summary|dialog|iframe)\b[^<>]*/>",
    re.I,
)


def chk_self_closing(html):
    """Flag JSX-style self-closing tags on non-void HTML elements (browser ignores the `/`)."""
    out = []
    for m in NONVOID_SELF_CLOSING.finditer(html):
        line = html.count("\n", 0, m.start()) + 1
        snippet = m.group(0)
        if len(snippet) > 72:
            snippet = snippet[:69] + "..."
        out.append(
            f"L{line} JSX-style self-closing tag {snippet}"
            f" (in HTML the / in <{m.group(1).lower()}/> is ignored by the browser, the tag stays open,"
            " and all following content gets swallowed into that element, wrecking the layout;"
            " use a matching pair of tags instead)"
        )
    return out


RULES = [
    ("tailwind-v3-pinned",   "error", False, chk_tailwind_version),
    ("self-contained",       "error", False, chk_local_refs),
    ("stamp-required",       "error", False, chk_stamp),
    ("design-tokens-block",  "error", False, chk_tokens_block),
    ("html-integrity",       "error", False, chk_html_integrity),
    ("section-ids",          "error", False, chk_section_ids),
    ("no-jsx-self-closing",  "error", False, chk_self_closing),
    ("fonts-from-library",   "error", False, chk_font_library),
    ("font-registration",   "error", False, chk_font_face_required),
    ("no-base64-image",      "error", False, chk_base64_img),
    ("min-text-size",        "error", False, chk_tiny_text),
    ("spacing-scale",        "error", False, chk_spacing_scale),
    ("config-integrity",     "error", False, chk_config_integrity),
    ("config-js-syntax",     "error", False, chk_config_js_syntax),
    ("keyframes-wired",      "error", False, chk_keyframes_wired),
    ("intersect-start-state", "error", False, chk_intersect_start_state),
    ("motion-window-timing", "error", False, chk_motion_window_timing),
    ("color-fn-double-wrap", "error", False, chk_color_fn_double_wrap),
    ("no-inline-hex",        "error", True,  chk_inline_hex),
    ("no-direct-palette",    "error", True,  chk_direct_palette),
    ("no-gradient-text",     "error", True,  chk_gradient_text),
    ("no-purple-gradient",   "error", True,  chk_purple_gradient),
    ("no-lorem",             "error", True,  chk_lorem),
    ("no-emoji-icons",       "error", True,  chk_emoji_icons),
]


def check_file(path, report):
    """Run every rule against one draft file and append its entry to report."""
    html = Path(path).read_text(encoding="utf-8")
    waivers = {name: reason for name, reason in DISABLE.findall(html)}
    entry = {"file": str(path), "errors": [], "warnings": [], "waived": []}
    for name, severity, waivable, fn in RULES:
        issues = fn(html)
        if not issues:
            continue
        if name in waivers and waivable:
            entry["waived"].append({"rule": name, "reason": waivers[name], "issues": issues})
            continue
        if name in waivers and not waivable:
            issues = [f"(this rule is not waivable) {i}" for i in issues]
        entry["errors" if severity == "error" else "warnings"].extend(f"[{name}] {i}" for i in issues)
    m = STAMP.search(html)
    entry["title"] = m.group(1).strip() if m else None
    entry["skeleton"] = m.group(2).strip() if m else None
    entry["sig"] = m.group(3).strip() if m else None
    report["files"].append(entry)
    return entry


def check_multi_diversity(entries, report):
    """Multi-draft (>=2, typically the first round's three) anti-reskinning gate: sigs must differ.

    Only sig is checked, the one deterministically judgeable signal of "same template copied N
    times with new copy". No aesthetic verdict on palette / font / skeleton spread -- whether the
    vibe should diverge depends on which axes the user's query pinned down, which a rule cannot
    decide; structural spread is left to the differentiation engine's five-axis matrix and the
    model's own discipline.
    """
    def _norm_sig(s):
        return re.sub(r"\s+", "", s or "").lower()

    sigs = [(e["file"], _norm_sig(e.get("sig"))) for e in entries if _norm_sig(e.get("sig"))]
    seen, dups = {}, []
    for f, s in sigs:
        if s in seen:
            dups.append(f"{Path(seen[s]).name} and {Path(f).name} have the same sig")
        else:
            seen[s] = f
    if dups:
        report["signature_diversity"] = (
            f"Duplicate sig: {dups} — each draft must have its own unique elevated craft detail;"
            " identical sigs mean only the skin changed, not the soul."
            " Rewrite the signature of one of the drafts"
        )


DIVERSITY_KEYS = ("signature_diversity",)

MANIFEST_FILENAME = "manifest.json"
STATUS_GENERATING = "generating"
STATUS_READY = "ready"
# Read-side compat with manifests written before the engineering rename
_READY_ALIASES = {STATUS_READY, "valid"}


def _manifest_path(report):
    """Path of manifest.json in the design dir the checked drafts live in.

    Derived from the checked files rather than from the app root, so a run against an
    unrelated directory (local debugging) never touches an app's manifest. Returns None
    when the checked files do not share one directory.
    """
    dirs = {str(Path(e["file"]).parent) for e in report["files"] if e.get("file")}
    if len(dirs) != 1:
        return None
    return Path(dirs.pop()) / MANIFEST_FILENAME


def _verdicts(report):
    """Per-file pass verdict: error-free and not held back by a cross-draft gate.

    A cross-draft failure (duplicate sig) cannot be attributed to one draft, so it holds
    back every draft in the run -- matching what the engineering hook did when it read
    this report from stdout.
    """
    cross_draft_block = any(
        b.get("file") not in {Path(e["file"]).name for e in report["files"]}
        for b in report["blocking"]
    )
    return {
        Path(e["file"]).name: (e.get("error_count") == 0 and not cross_draft_block)
        for e in report["files"]
    }


def update_manifest(report):
    """Write this run's verdicts into manifest.json, in place, next to the drafts.

    The engineering side owns registration (designId / parent_ids / next_id / appType) and
    the frontend signal; this script owns exactly one thing -- turning a verdict into
    `status` + `check_failed`. It only touches drafts already registered: an unregistered
    draft has no id to key off, and it could not have passed anyway (its stamp is still the
    placeholder new_draft.py wrote). Doing this in-process is the point: a `--check` further
    down the same shell command sees the result immediately, no matter how the model piped
    or chained the commands.

    Silent no-op when the manifest is absent (standalone/local runs) or unreadable -- the
    engineering round-end sweep re-runs this checker for drafts still left at generating.
    """
    path = _manifest_path(report)
    if path is None or not path.is_file():
        return
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(manifest, dict) or not isinstance(manifest.get("drafts"), list):
        return

    now = _now_iso()
    verdicts = _verdicts(report)
    by_name = {}
    for entry in manifest["drafts"]:
        if isinstance(entry, dict):
            by_name[str(entry.get("path") or "").rsplit("/", 1)[-1]] = entry

    changed = False
    for filename, passed in verdicts.items():
        entry = by_name.get(filename)
        if entry is None:
            continue
        if passed:
            fields = {"status": STATUS_READY, "check_failed": False, "reason": None}
            stamp_title = next(
                (e.get("title") for e in report["files"]
                 if Path(e["file"]).name == filename and e.get("title")),
                None,
            )
            if stamp_title:
                fields["title"] = stamp_title
        elif entry.get("status") == STATUS_GENERATING:
            fields = {"check_failed": True}
        else:
            # Already sealed (ready/failed): a later failing run must not un-seal it
            continue
        if all(entry.get(k) == v for k, v in fields.items()):
            continue
        entry.update(fields)
        entry["updated_at"] = now
        changed = True

    if not changed:
        return
    # Atomic replace: a torn write would leave the engineering side without its registry
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def _now_iso():
    """UTC timestamp in the same shape the engineering side writes (seconds precision)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main():
    """CLI entry: run all rules against the given HTML files and print a JSON report."""
    paths = sys.argv[1:]
    if not paths:
        print(__doc__)
        sys.exit(2)
    report = {"ok": True, "blocking": [], "files": []}
    entries = []
    for p in paths:
        resolved = resolve_input_path(p)
        if not Path(resolved).exists():
            report["files"].append(
                {"file": p, "errors": [f"File does not exist: {p}"], "warnings": [], "waived": []}
            )
            continue
        entries.append(check_file(resolved, report))

    if len(entries) >= 2:
        check_multi_diversity(entries, report)

    # blocking is the sole source of failure reasons; files[] keeps only identifiers and
    # waiver records, not duplicated errors text
    for e in report["files"]:
        for err in e.get("errors", []):
            rule = err.split("]", 1)[0].lstrip("[") if err.startswith("[") else "file"
            report["blocking"].append({"rule": rule, "file": Path(e["file"]).name, "reason": err})
    for key in DIVERSITY_KEYS:
        if key in report:
            report["blocking"].append({"rule": key, "file": "<multi-draft>", "reason": report[key]})

    report["ok"] = not report["blocking"]
    for e in report["files"]:
        e["error_count"] = len(e.pop("errors", []))
        e.pop("warnings", None)
        if not e.get("waived"):
            e.pop("waived", None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    update_manifest(report)
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
