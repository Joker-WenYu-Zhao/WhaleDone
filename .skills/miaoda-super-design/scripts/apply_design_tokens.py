#!/usr/bin/env python3
"""miaoda-super-design: token injection / validation script (pure stdlib, zero third-party deps).

Usage:
  Validate (pre-delivery self-check / registration hook):
    python3 apply_design_tokens.py --check --html design/home-1.html
  Inject (on draft conversion, rebuild the index.css token block + extend tailwind.config.js):
    python3 apply_design_tokens.py --html design/home-4.html \
        --index-css src/index.css --tailwind-config tailwind.config.js
  Emit DESIGN.md front-matter tokens section:
    python3 apply_design_tokens.py --emit-designmd-tokens --html design/home-4.html

Conventions:
- DESIGN-TOKENS block = design-decision core set; CUSTOM-TOKENS block = newly registered tokens
  (declaration = registration).
- Value precision: design-decision value > rule-derived value > baseline default.
- Atomicity: if any step fails, neither index.css nor tailwind.config.js is written; exit != 0.
"""

import argparse
import colorsys
import json
import os
import re
import sys
from pathlib import Path

APP_ROOT_RE = re.compile(r"^app-[\w-]+$")


def _walk_up_for_app(start):
    """Walk from `start` upward looking for the first `app-<id>` directory; returns None if not found."""
    probe = os.path.abspath(start)
    while True:
        if APP_ROOT_RE.match(os.path.basename(probe)):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent


def find_app_root():
    """Locate the current app root `app-<id>`: check CWD ancestors first, then the script's own ancestors.

    CWD is unreliable — the engineering side may run bash from the app's parent directory
    (e.g. `/workspace`), in which case `app-<id>` is a child of CWD and walking upward
    from CWD never reaches it. But the script itself lives at
    `<app-root>/.skills/miaoda-super-design/scripts/`, so `__file__`'s ancestors always
    contain `app-<id>` — a more reliable anchor than CWD. Only when both fail (local
    debugging, or the skill isn't inside an app at all) do we fall back to CWD.
    """
    hit = _walk_up_for_app(os.getcwd())
    if hit:
        return hit
    hit = _walk_up_for_app(os.path.dirname(os.path.abspath(__file__)))
    if hit:
        return hit
    return os.path.abspath(os.getcwd())


def resolve_input_path(arg):
    """Absolute paths are used as-is; relative paths resolve against the app root
    (not CWD, which may be the app's parent)."""
    if os.path.isabs(arg):
        return os.path.abspath(arg)
    return os.path.join(find_app_root(), arg)


DT_BLOCK = re.compile(r"/\*\s*=====\s*DESIGN-TOKENS:BEGIN\s*=====(.*?)=====\s*DESIGN-TOKENS:END\s*=====\s*\*/", re.S)
CT_BLOCK = re.compile(r"/\*\s*=====\s*CUSTOM-TOKENS:BEGIN\s*=====(.*?)=====\s*CUSTOM-TOKENS:END\s*=====\s*\*/", re.S)
VAR_DECL = re.compile(r"--([a-z0-9-]+)\s*:\s*([^;]+);")
HSL_TRIPLET = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)%\s+([0-9]+(?:\.[0-9]+)?)%\s*$")
HEX_COLOR = re.compile(r"^\s*#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\s*$")
HEX_COLOR_ALPHA = re.compile(r"^\s*#([0-9a-fA-F]{8}|[0-9a-fA-F]{4})\s*$")
KEBAB = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

# Utility-class prefixes that consume theme.colors: a `bg-<token>` class only produces CSS
# if Tailwind finds a matching entry in theme.extend.colors at compile time; otherwise it
# silently produces nothing. Does not include families on other scales (grid-cols / gap etc.).
COLOR_UTILITY_PREFIXES = (
    "bg", "text", "border", "ring", "fill", "stroke", "outline", "accent",
    "caret", "decoration", "divide", "from", "to", "via", "shadow", "placeholder",
)


def used_as_color_utility(name, class_text):
    """Is a token used as a color utility class (`bg-<name>` / `md:text-<name>` / `border-<name>/50`)?

    Only this usage depends on registration in tailwind.config.colors; `var(--name)` and
    hand-written CSS rules (`.ink-stroke{color:var(--ink)}`) resolve at runtime and are
    unrelated to Tailwind compilation, so they don't need registration.
    """
    for prefix in COLOR_UTILITY_PREFIXES:
        # Leading boundary includes `:` (catches md:/hover: variants); trailing allows `/`
        # (opacity modifier bg-x/50)
        if re.search(rf"(?:^|[\s:]){prefix}-{re.escape(name)}(?=$|\s|/)", class_text):
            return True
    return False

# rgb()/rgba(): comma- or space-separated (CSS Color-4 dual syntax), optional `/ alpha`,
# function name case-insensitive. Values may be numeric or percentage (CSS allows r/g/b as
# percentages); alpha may be a decimal or a percentage.
RGB_FUNC = re.compile(
    r"^\s*rgba?\(\s*([0-9.]+%?)\s*[, ]\s*([0-9.]+%?)\s*[, ]\s*([0-9.]+%?)\s*"
    r"(?:[,/]\s*([0-9.]+%?)\s*)?\)\s*$",
    re.I,
)
# hsl()/hsla(): also comma- or space-separated (CSS Color-4); H may carry a deg unit.
HSL_FUNC = re.compile(
    r"^\s*hsla?\(\s*([0-9.]+)(?:deg)?\s*[, ]\s*([0-9.]+)%\s*[, ]\s*([0-9.]+)%\s*"
    r"(?:[,/]\s*([0-9.]+%?)\s*)?\)\s*$",
    re.I,
)
# Composite visual value — gradient / repeating texture. This kind of value is itself a
# composite of "multiple colors + direction + stops", with no single HSL triplet to
# normalize to; it only needs to pass registration criteria (2) and (3) below, and is
# exempt from color-format validation.
GRADIENT_VALUE = re.compile(r"(linear|radial|repeating-linear|repeating-radial|conic)-gradient\(", re.I)
# Structural-integrity probe (used on the pass-through branch): parentheses/quotes must be
# balanced and the value must be non-empty — this is the only hard gate. Any other "we
# don't recognize this format but the structure is intact" legitimate CSS value (e.g. an
# unenumerated new function like color-mix()) is passed through rather than flagged as an
# error just because it isn't on the list.
_PAIR_CHARS = {"(": ")", '"': '"', "'": "'"}


def _structurally_valid_css_value(value):
    """Coarse validation: parentheses/quotes balanced, non-empty. Only a real failure fails this."""
    v = (value or "").strip()
    if not v:
        return False
    stack, quote = [], None
    for ch in v:
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch == "(":
            stack.append(ch)
        elif ch == ")":
            if not stack:
                return False
            stack.pop()
    return not stack and quote is None

# Non-color tokens (value is not an HSL triplet)
NON_COLOR = {"radius"}

# Tokens consumed by tailwind.config but not defined in the baseline index.css — "known optional"
CONFIG_KNOWN_OPTIONAL = {"success", "warning", "info"}

# Rule-derivation map: target token <- source token (applies when the design does not declare the target explicitly)
DERIVATION = {
    "popover": "card",
    "popover-foreground": "card-foreground",
    "sidebar-background": "background",
    "sidebar-foreground": "foreground",
    "sidebar-primary": "primary",
    "sidebar-primary-foreground": "primary-foreground",
    "sidebar-accent": "accent",
    "sidebar-accent-foreground": "accent-foreground",
    "sidebar-border": "border",
    "sidebar-ring": "ring",
}

# Design-decision core set (a missing entry is only a warning; the baseline default fills in)
CORE_SET = [
    "radius", "background", "foreground", "card", "card-foreground",
    "primary", "primary-foreground", "secondary", "secondary-foreground",
    "muted", "muted-foreground", "accent", "accent-foreground",
    "destructive", "destructive-foreground", "border", "input", "ring",
]


def hex_to_hsl_triplet(hex_str):
    """#RGB / #RRGGBB / #RGBA / #RRGGBBAA -> (bare HSL triplet, alpha or None)."""
    h = hex_str.strip().lstrip("#")
    alpha = None
    if len(h) == 4:  # #RGBA: single-char per channel; alpha is the last char, needs doubling
        alpha = round(int(h[3] * 2, 16) / 255.0, 3)
        h = h[:3]
    elif len(h) == 8:  # #RRGGBBAA: alpha is the last two hex digits
        alpha = round(int(h[6:8], 16) / 255.0, 3)
        h = h[:6]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    hue, lig, sat = colorsys.rgb_to_hls(r, g, b)
    trip = f"{round(hue * 360, 1):g} {round(sat * 100, 1):g}% {round(lig * 100, 1):g}%"
    return trip, alpha


def _pct_or_num(s, scale255=False):
    """CSS numeric token ('80%' or '204') -> 0-1 float; with scale255, normalize against 0-255."""
    s = s.strip()
    if s.endswith("%"):
        return float(s[:-1]) / 100.0
    return float(s) / 255.0 if scale255 else float(s)


def _fmt_alpha(raw):
    """alpha token ('0.5' or '50%') -> unified decimal string, trailing zeros stripped."""
    if raw is None:
        return None
    v = _pct_or_num(raw) if raw.strip().endswith("%") else float(raw.strip())
    return f"{v:g}"


def parse_block(block_text):
    """A block may contain :root{} and .dark{} sections; with no selector it is treated as :root."""
    root, dark = {}, {}
    dark_m = re.search(r"\.dark\s*\{([^}]*)\}", block_text)
    dark_body = dark_m.group(1) if dark_m else ""
    root_body = block_text[:dark_m.start()] if dark_m else block_text
    for name, value in VAR_DECL.findall(root_body):
        root[name] = value.strip()
    for name, value in VAR_DECL.findall(dark_body):
        dark[name] = value.strip()
    return root, dark


CUSTOM_MARKER = "/* custom tokens | registered by miaoda-super-design */"
# Old-format marker (separator ·, U+00B7) — non-ASCII characters get easily mangled along
# editing pipelines and break matching, so this format is deprecated. Still needs to be
# recognized for backward compatibility with legacy project index.css files; otherwise
# they'd be misjudged as "not registered" and the custom block would be duplicated on
# re-injection.
CUSTOM_MARKER_LEGACY = "/* custom tokens · registered by miaoda-super-design */"


def parse_index_css(css_text):
    """Baseline index.css -> (root_order, root_map, dark_order, dark_map, registered_customs).

    :root variables after CUSTOM_MARKER are custom tokens injected in the past — they are
    "already registered" rather than part of the baseline schema, so repeat declarations in
    CUSTOM-TOKENS are allowed (idempotent) on re-injection / cross-draft reuse.
    """
    def grab(body):
        pairs = VAR_DECL.findall(body)
        return [n for n, _ in pairs], {n: v.strip() for n, v in pairs}

    registered = {}
    m = re.search(r":root\s*\{([^}]*)\}", css_text)
    root_body = m.group(1) if m else ""
    marker = CUSTOM_MARKER if CUSTOM_MARKER in root_body else (
        CUSTOM_MARKER_LEGACY if CUSTOM_MARKER_LEGACY in root_body else None
    )
    if marker:
        root_body, custom_body = root_body.split(marker, 1)
        registered = {n: v.strip() for n, v in VAR_DECL.findall(custom_body)}
    ro, rm = grab(root_body)
    md = re.search(r"\.dark\s*\{([^}]*)\}", css_text)
    do, dm = grab(md.group(1) if md else "")
    return ro, rm, do, dm, registered


# All :root/.dark token names in the app's baseline index.css (hardcoded). During the design
# phase the workspace has no engineering code yet, so --index-css is unavailable and the only
# way to tell "which names belong to the baseline schema vs. custom" is this constant.
# Keep in sync with the baseline template src/index.css; update here when the template changes.
BASELINE_NAMES = frozenset({
    "radius",
    "background", "foreground",
    "card", "card-foreground",
    "popover", "popover-foreground",
    "primary", "primary-foreground",
    "secondary", "secondary-foreground",
    "muted", "muted-foreground",
    "accent", "accent-foreground",
    "destructive", "destructive-foreground",
    "border", "input", "ring",
    "chart-1", "chart-2", "chart-3", "chart-4", "chart-5",
    "sidebar-background", "sidebar-foreground",
    "sidebar-primary", "sidebar-primary-foreground",
    "sidebar-accent", "sidebar-accent-foreground",
    "sidebar-border", "sidebar-ring",
})


def load_baseline(index_css_path):
    """-> (set of schema token names, map of already-registered custom tokens).

    With --index-css (P4 injection phase, engineering code already checked out) read the
    real file, which can recognize previously injected custom tokens; without it (P2/P3
    design phase) use the hardcoded BASELINE_NAMES, depending on no engineering file
    existing in the workspace.
    """
    if index_css_path and Path(index_css_path).exists():
        ro, rm, do, dm, registered = parse_index_css(Path(index_css_path).read_text(encoding="utf-8"))
        return set(ro) | set(do), registered
    return set(BASELINE_NAMES), {}


def validate(html_text, baseline_names, registered_customs, report):
    """Validate a draft's DESIGN-TOKENS/CUSTOM-TOKENS blocks, appending errors/warnings to report."""
    m_dt = DT_BLOCK.search(html_text)
    if not m_dt:
        report["errors"].append("missing DESIGN-TOKENS block (===== DESIGN-TOKENS:BEGIN/END ===== markers)")
        return {}, {}, {}
    design_root, design_dark = parse_block(m_dt.group(1))

    m_ct = CT_BLOCK.search(html_text)
    custom_root = parse_block(m_ct.group(1))[0] if m_ct else {}

    known = set(baseline_names) | set(DERIVATION) | CONFIG_KNOWN_OPTIONAL | NON_COLOR
    known -= set(registered_customs)  # previously injected custom tokens are not part of the baseline schema

    def norm_value(name, value, owner):
        if name in NON_COLOR:
            if not re.match(r"^[0-9.]+(rem|px|em)$", value):
                report["errors"].append(f"{owner} --{name}: invalid length value '{value}'")
            return value
        # Self-reference: the value is var(--itself), so the declaration can never resolve
        # to an actual color (the browser ignores it and falls back to initial/inherited).
        # Parentheses are balanced and the value is non-empty — without this check, the
        # §structural-integrity fallback would misjudge it as a "valid unenumerated value"
        # and let it through.
        self_ref = re.match(r"^\s*var\(\s*--" + re.escape(name) + r"\s*\)\s*$", value or "")
        if self_ref:
            report["errors"].append(
                f"{owner} --{name}: value is 'var(--{name})' self-reference——the declaration can never resolve "
                "to an actual color; the browser will ignore it and fall back to initial/inherited value. "
                "Replace with a concrete color value (hex/rgb/hsl)"
            )
            return value
        if HSL_TRIPLET.match(value):
            return re.sub(r"\s+", " ", value.strip())
        hx = HEX_COLOR.match(value)
        if hx:
            trip, _ = hex_to_hsl_triplet(value)
            report["warnings"].append(f"{owner} --{name}: hex '{value.strip()}' normalized to HSL '{trip}'")
            return trip
        hxa = HEX_COLOR_ALPHA.match(value)
        if hxa:
            trip, alpha = hex_to_hsl_triplet(value)
            out_val = f"{trip} / {alpha:g}" if alpha is not None else trip
            report["warnings"].append(f"{owner} --{name}: hex '{value.strip()}' normalized to HSL '{out_val}'")
            return out_val
        # rgb()/rgba(): comma- or space-separated (CSS Color-4); the color part converts to
        # HSL and alpha is kept as-is. Still "a single color + opacity", so it normalizes at
        # the same level as hex (e.g. --nav-border: rgba(0,255,136,0.12)).
        rgb_m = RGB_FUNC.match(value)
        if rgb_m:
            rr, gg, bb, aa = rgb_m.groups()
            r255 = round(_pct_or_num(rr, scale255=True) * 255)
            g255 = round(_pct_or_num(gg, scale255=True) * 255)
            b255 = round(_pct_or_num(bb, scale255=True) * 255)
            trip, _ = hex_to_hsl_triplet("#{:02x}{:02x}{:02x}".format(r255, g255, b255))
            a_str = _fmt_alpha(aa)
            out_val = f"{trip} / {a_str}" if a_str else trip
            report["warnings"].append(f"{owner} --{name}: '{value.strip()}' normalized to HSL '{out_val}'")
            return out_val
        # hsl()/hsla(): the function-wrapped equivalent; unwrap into a bare triplet (same
        # thing expressed twice — we don't accept both formats coexisting).
        hsl_m = HSL_FUNC.match(value)
        if hsl_m:
            hh, ss, ll, aa = hsl_m.groups()
            trip = f"{float(hh):g} {float(ss):g}% {float(ll):g}%"
            a_str = _fmt_alpha(aa)
            out_val = f"{trip} / {a_str}" if a_str else trip
            report["warnings"].append(f"{owner} --{name}: '{value.strip()}' normalized to HSL '{out_val}'")
            return out_val
        # Gradient / repeating texture: composite value of multiple layered colors, no
        # single HSL triplet to normalize to. Exempt from color-format validation; still
        # subject to registration criteria (2) and (3) below (tailwind registration + actual
        # page usage).
        if GRADIENT_VALUE.search(value):
            return value.strip()
        # Fallback: none of the rules above matched, but the value itself has balanced
        # parens/quotes and is non-empty — this is a legitimate CSS form the script hasn't
        # enumerated (e.g. color-mix(), a future new syntax), not a broken value.
        # Let it through, log only a warning as a paper trail; don't raise an error and
        # force the model to rewrite something that is already correct.
        if _structurally_valid_css_value(value):
            report["warnings"].append(
                f"{owner} --{name}: '{value.strip()}' is not one of the enumerated formats "
                "(hex/rgb/hsl/gradient); structure is intact, accepted as a valid value——if this is a color "
                "value, prefer one of the formats above for unified management"
            )
            return value.strip()
        report["errors"].append(
            f"{owner} --{name}: value '{value}' has unbalanced parentheses/quotes——the value itself is malformed")
        return value

    for name in list(design_root):
        if name not in known:
            report["errors"].append(
                f"DESIGN-TOKENS --{name}: not in the baseline schema. "
                "A new token must go in the CUSTOM-TOKENS block (declaration = registration)")
        design_root[name] = norm_value(name, design_root[name], "DESIGN-TOKENS")
    for name in list(design_dark):
        if name not in known:
            report["errors"].append(f"DESIGN-TOKENS(.dark) --{name}: not in the baseline schema")
        design_dark[name] = norm_value(name, design_dark[name], "DESIGN-TOKENS(.dark)")

    body = html_text
    # class attribute text: the basis for criterion (2) "is it used as a utility class".
    # Only looks inside class attributes, not var() references or hand-written CSS rules.
    class_attr_text = " ".join(re.findall(r'(?<![\w-])class=["\']([^"\']*)["\']', body))
    for name in list(custom_root):
        if not KEBAB.match(name):
            report["errors"].append(f"CUSTOM-TOKENS --{name}: name must be kebab-case")
        if name in known:
            report["errors"].append(
                f"CUSTOM-TOKENS --{name}: collides with a baseline token, should be written in the DESIGN-TOKENS block")
        raw_value = custom_root[name]
        normed = norm_value(name, raw_value, "CUSTOM-TOKENS")
        custom_root[name] = normed
        # Color-type values (already normalized by this function into an "HSL triplet" or
        # "HSL triplet / alpha") are wrapped as hsl(var(--name)); everything else
        # (gradients / unenumerated legal values like color-mix()) is already a complete
        # CSS value, so wrapping in hsl() syntax doesn't make sense — the draft must write
        # the bare var(--name). The criterion is the normalized value's shape (not the
        # original format), the same criterion source build_tailwind_config uses, so the
        # two conclusions are guaranteed to agree.
        is_color = bool(HSL_TRIPLET.match(normed.split(" / ", 1)[0].strip()))
        # Criterion (2): tailwind.config registration is only required when the token is
        # **used as a color utility class**. A token only referenced via `var(--name)`
        # (inline style / hand-written CSS rule) resolves at runtime, bypasses Tailwind
        # compilation, and renders fine whether registered or not — requiring registration
        # unconditionally would produce a false-positive error, and since the draft is
        # already sealed after delivery, the only fix would be a whole new draft just to
        # add an entry that was never actually needed.
        expected_ref = f"hsl(var(--{name}))" if is_color else f"var(--{name})"
        if used_as_color_utility(name, class_attr_text) and expected_ref not in body:
            report["errors"].append(
                f"CUSTOM-TOKENS --{name}: used as a color utility class but missing from the draft's "
                f"tailwind.config theme.extend.colors — Tailwind emits no CSS for it and the class "
                f"silently no-ops. Add to colors: {name}: '{expected_ref}'")
        usage = re.compile(r"(class=[\"'][^\"']*\b[\w-]*" + re.escape(name) + r"\b|var\(--" + re.escape(name) + r"\))")
        body_after_head = body.split("</head>", 1)[-1]
        if not usage.search(body_after_head):
            report["warnings"].append(
                f"CUSTOM-TOKENS --{name}: not actually used on the page "
                "(registration three-part contract ③); confirm whether it is redundant")

    # Stray new variable names (used without being declared)
    declared = set(design_root) | set(design_dark) | set(custom_root) | known | set(registered_customs)
    for name in set(re.findall(r"var\(--([a-z0-9-]+)\)", html_text)):
        if name not in declared and not name.startswith(("tw-", "radix-")):
            report["errors"].append(
                f"Unregistered variable var(--{name}): declare it in the CUSTOM-TOKENS block before use")

    for name in CORE_SET:
        if name not in design_root:
            report["warnings"].append(f"Core set is missing --{name} (baseline default will be used)")

    return design_root, design_dark, custom_root


def build_index_css(css_text, design_root, design_dark, custom_root, report):
    """Render the validated tokens back into index.css's :root/.dark blocks."""
    ro, rm, do, dm, registered = parse_index_css(css_text)
    if not ro:
        report["errors"].append("--index-css file: cannot parse a :root block")
        return None
    # Previously injected custom tokens are not discarded (app code may already consume
    # them); same-named values declared by this draft win
    custom_root = {**registered, **custom_root}

    def resolve(name, design_map, base_map):
        if name in design_map:
            return design_map[name], "design"
        if name in DERIVATION and DERIVATION[name] in design_map:
            return design_map[DERIVATION[name]], "derived"
        return base_map.get(name), "default"

    def render(order, design_map, base_map, indent):
        lines = []
        names = list(order) + [n for n in design_map if n not in order]  # append promoted declarations (e.g. success)
        for name in names:
            value, _src = resolve(name, design_map, base_map)
            if value is None:
                continue
            lines.append(f"{indent}--{name}: {value};")
        return lines

    root_lines = render(ro, design_root, rm, "    ")
    if custom_root:
        root_lines.append("    " + CUSTOM_MARKER)
        root_lines.extend(f"    --{n}: {v};" for n, v in custom_root.items())
    dark_lines = render(do, design_dark, dm, "    ")

    def replace_block(text, selector, lines):
        pat = re.compile(r"(" + re.escape(selector) + r"\s*\{\n)([^}]*)(  \})")
        if not pat.search(text):
            pat = re.compile(r"(" + re.escape(selector) + r"\s*\{\n?)([^}]*)(\})")
        return pat.sub(lambda m: m.group(1) + "\n".join(lines) + "\n" + m.group(3), text, count=1)

    out = replace_block(css_text, ":root", root_lines)
    out = replace_block(out, ".dark", dark_lines)
    return out


def build_tailwind_config(cfg_text, custom_root, report):
    """Idempotently write custom tokens into theme.extend.colors.

    custom_root's values are already normalized by norm_value() at this point: color-type
    values are unified into "HSL triplet" or "HSL triplet / alpha"; gradients and
    unenumerated values remain as-is (and won't match the HSL-triplet regex).
    The "is it HSL triplet shape?" check here determines whether to wrap in hsl() or bare
    var(); it is the same criterion (just evaluated on the post-normalization form) as
    validate() uses on the pre-normalization form — the two must agree, otherwise the
    injected format and the expected reference format used by validation would conflict.
    """
    if not custom_root:
        return cfg_text
    m = re.search(r"(extend:\s*\{[\s\S]*?colors:\s*\{\n)", cfg_text)
    if not m:
        report["errors"].append("--tailwind-config: cannot find the theme.extend.colors insertion point")
        return None
    additions = []
    for name, value in custom_root.items():
        head = value.split(" / ", 1)[0].strip()
        is_color = bool(HSL_TRIPLET.match(head))
        ref = f"hsl(var(--{name}))" if is_color else f"var(--{name})"
        if ref in cfg_text:
            continue  # already injected, skip idempotently
        additions.append(f"                '{name}': '{ref}',")
    if not additions:
        return cfg_text
    insert_at = m.end(1)
    block = "                /* custom tokens | registered by miaoda-super-design */\n" + "\n".join(additions) + "\n"
    return cfg_text[:insert_at] + block + cfg_text[insert_at:]


# Semantic-section root element: any opening tag carrying id= counts
# (section/header/footer/main/div, ...). Matching only <section> would miss hero — drafts
# often write hero as <header id="hero">, and hero is exactly the section
# most in need of a class contract.
#
# The id= regex uses a negative lookbehind so it does NOT match `data-xxx-id=` /
# `aria-labelledby=` etc. (hyphens are word boundaries, so plain \bid would falsely
# catch the tail of `data-section-id=`).
#
# Open/close tag location uses a "quote-aware" scan (a non-greedy [^>]* would be cut off
# early by a literal > inside an attribute value, e.g. title="x > y"): step through
# character by character to find the opening tag's >, skipping > inside double- or
# single-quoted strings.
TAG_OPEN_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)(\s)", re.IGNORECASE)
SECTION_ID_RE = re.compile(r'(?<![\w-])id=["\']([^"\']+)["\']', re.IGNORECASE)
BLOCK_CLASS_RE = re.compile(r'\sclass=["\']([^"\']*)["\']', re.IGNORECASE)


def _find_tag_end(html_text, start):
    """From `start` (after the tag name), find the opening tag's closing `>`, skipping `>` inside quotes."""
    i, n, quote = start, len(html_text), None
    while i < n:
        ch = html_text[i]
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == ">":
            return i
        i += 1
    return -1


def _iter_tags_with_section_id(html_text):
    """Yield each opening tag carrying id=, along with its full attribute string (tag name to `>`)."""
    for m in TAG_OPEN_RE.finditer(html_text):
        end = _find_tag_end(html_text, m.end())
        if end < 0:
            continue
        attrs = html_text[m.start(1):end]
        sid_m = SECTION_ID_RE.search(attrs)
        if sid_m:
            yield sid_m.group(1), attrs


def extract_section_blueprint(html_text):
    """Extract the id -> root element class mapping for DESIGN.md's section_blueprint section.

    Key = id (which doubles as the in-page anchor target); value = the verbatim class
    text on that opening tag (no filtering, no reordering). Sections without a class
    are skipped (no class contract to enforce). Document order is preserved.
    Multi-line class values are collapsed onto one line (IDE formatting may wrap them).
    """
    blueprint = {}
    for section_id, attrs in _iter_tags_with_section_id(html_text):
        cm = BLOCK_CLASS_RE.search(attrs)
        if cm and cm.group(1).strip() and section_id not in blueprint:
            # Collapse to one line: an IDE may wrap a long class list, and the emitted
            # value must not contain newlines or it breaks the YAML
            cls = " ".join(cm.group(1).split())
            blueprint[section_id] = cls
    return blueprint


def emit_designmd(design_root, design_dark, custom_root, html_text=""):
    """Render the DESIGN.md front-matter tokens/custom_tokens/section_blueprint block."""
    lines = ["tokens:"]
    for name in CORE_SET:
        if name in design_root:
            lines.append(f'  {name}: "{design_root[name]}"')
    for name, value in design_root.items():
        if name not in CORE_SET:
            lines.append(f'  {name}: "{value}"')
    for name, value in design_dark.items():
        lines.append(f'  dark-{name}: "{value}"')
    if custom_root:
        lines.append("custom_tokens:")
        lines.extend(f'  {n}: "{v}"' for n, v in custom_root.items())
    # section_blueprint
    blueprint = extract_section_blueprint(html_text)
    lines.append("section_blueprint:")
    if blueprint:
        for sid, cls in blueprint.items():
            lines.append(f'  {sid}: "{cls}"')
    else:
        lines.append("  # (no sections with id= found)")
    return "\n".join(lines)


def main():
    """CLI entry: validate a draft's tokens and either check, emit DESIGN.md tokens, or inject."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", required=True, help="Path to the design draft HTML")
    ap.add_argument("--check", action="store_true", help="Validate only, do not write to disk")
    ap.add_argument("--emit-designmd-tokens", action="store_true",
                    help="Emit the tokens section for DESIGN.md front matter")
    ap.add_argument("--index-css",
                    help="Path to the app's src/index.css (injection target / schema source for validation)")
    ap.add_argument("--tailwind-config",
                    help="Path to the app's tailwind.config.js (injection target for custom tokens)")
    args = ap.parse_args()

    report = {"ok": True, "errors": [], "warnings": [], "design_tokens": {}, "dark_tokens": {}, "custom_tokens": {}}

    # Path arguments resolved once: absolute paths as-is, relative paths against the app root;
    # all subsequent reads/writes use the resolved result
    index_css_arg = resolve_input_path(args.index_css) if args.index_css else None
    tailwind_cfg_arg = resolve_input_path(args.tailwind_config) if args.tailwind_config else None

    html_path = Path(resolve_input_path(args.html))
    if not html_path.exists():
        report["errors"].append(f"html does not exist: {html_path}")
        _finish(report)
    html_text = html_path.read_text(encoding="utf-8")

    baseline_names, registered_customs = load_baseline(index_css_arg)
    design_root, design_dark, custom_root = validate(html_text, baseline_names, registered_customs, report)
    report["design_tokens"], report["dark_tokens"], report["custom_tokens"] = design_root, design_dark, custom_root

    if report["errors"]:
        _finish(report)

    if args.emit_designmd_tokens:
        print(emit_designmd(design_root, design_dark, custom_root, html_text))
        sys.exit(0)

    if args.check:
        _finish(report)

    # Injection mode: write to disk only after everything builds successfully (atomicity)
    if not index_css_arg or not Path(index_css_arg).exists():
        report["errors"].append("injection mode requires --index-css and the file must exist")
        _finish(report)
    css_text = Path(index_css_arg).read_text(encoding="utf-8")
    new_css = build_index_css(css_text, design_root, design_dark, custom_root, report)

    new_cfg, cfg_path = None, None
    if custom_root:
        if not tailwind_cfg_arg or not Path(tailwind_cfg_arg).exists():
            report["errors"].append(
                "custom tokens present; injection mode requires --tailwind-config and the file must exist")
            _finish(report)
        cfg_path = Path(tailwind_cfg_arg)
        new_cfg = build_tailwind_config(cfg_path.read_text(encoding="utf-8"), custom_root, report)

    if report["errors"] or new_css is None or (custom_root and new_cfg is None):
        _finish(report)  # neither file is written

    Path(index_css_arg).write_text(new_css, encoding="utf-8")
    if cfg_path is not None:
        cfg_path.write_text(new_cfg, encoding="utf-8")
    report["written"] = [index_css_arg] + ([str(cfg_path)] if cfg_path else [])
    _finish(report)


def _finish(report):
    """Print the report as JSON and exit 0 on success, 1 if any error was recorded."""
    report["ok"] = not report["errors"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
