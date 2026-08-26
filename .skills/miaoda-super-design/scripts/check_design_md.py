#!/usr/bin/env python3
"""miaoda-super-design: DESIGN.md consistency validation (standard library only).

Usage:
    python3 check_design_md.py docs/DESIGN.md --index-css src/index.css [--src src/]

Checks:
1. Front matter exists and contains a tokens section;
2. Token values are bare HSL triplets (radius is a length value);
3. Consistency with src/index.css, variable by variable (every token declared
   in DESIGN.md must exist in index.css with the same value);
4. Section order: Overview → Colors → Typography → Layout → Components →
   Do's and Don'ts (sections may be omitted but not reordered);
5. Contrast: foreground/background and primary-foreground/primary must be
   >= 4.5:1 (WCAG AA);
6. When `--src` is given: front matter's `section_blueprint` is compared
   section-by-section against the React code — for each `id`,
   the root element's className must cover every class listed in the
   blueprint. A miss is a warning (a lost visual baseline, which should be
   fixed rather than waived by default).
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

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

    CWD is unreliable — the engineering side may run bash from the app's parent
    directory (e.g. `/workspace`), where `app-<id>` is a *child* of CWD and
    walking up never reaches it. The script itself is deployed under
    `<app-root>/.skills/miaoda-super-design/scripts/`, so `__file__` always has
    `app-<id>` among its ancestors, making it a sturdier anchor than CWD. Only
    when both probes fail (local debugging, or the skill living outside an app)
    do we fall back to CWD.
    """
    hit = _walk_up_for_app(os.getcwd())
    if hit:
        return hit
    hit = _walk_up_for_app(os.path.dirname(os.path.abspath(__file__)))
    if hit:
        return hit
    return os.path.abspath(os.getcwd())


def resolve_input_path(arg):
    """Keep absolute paths as-is; resolve relative paths against the app root
    (not CWD, since CWD may be the app's parent directory)."""
    if os.path.isabs(arg):
        return os.path.abspath(arg)
    return os.path.join(find_app_root(), arg)


HSL_TRIPLET = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)%\s+([0-9]+(?:\.[0-9]+)?)%\s*$")
SECTION_ORDER = ["Overview", "Colors", "Typography", "Layout", "Components", "Do's and Don'ts"]
NON_COLOR = {"radius"}

# JSX section parsing: regex cannot handle JSX (attribute values / expressions
# contain `>` and nested `{}`), so we use a state machine instead.
JSX_SECTION_OPEN = re.compile(r"<(?:section|header|footer|nav|aside|main)\b", re.I)
# id="X": negative lookbehind excludes data-xxx-id / aria-id etc.
# (hyphens count as word boundaries, so a plain \bid would match `data-section-id`).
JSX_SECTION_ID = re.compile(r'(?<![\w-])id\s*=\s*["\']([^"\']+)["\']')
STRING_LITERAL = re.compile(r"[\"'`]([^\"'`]*)[\"'`]")


def _jsx_tag_end(code, start):
    """From after `<section`, scan to the opening tag's `>`, skipping string
    literals and `{}` expressions (which may themselves contain `>`)."""
    i, n, quote, depth = start, len(code), None, 0
    while i < n:
        ch = code[i]
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == ">" and depth == 0:
            return i
        i += 1
    return -1


def _extract_classnames(attrs):
    """Collect every class token in className from a <section> attribute string.

    Supports className="..." / className={`...`} / className={cn("a", cond && "b")}.
    For the expression form: after finding `className={`, slice the whole
    brace-balanced expression and pull out every string literal inside it.
    """
    classes = set()
    for m in re.finditer(r"className\s*=\s*", attrs):
        j = m.end()
        if j >= len(attrs):
            break
        if attrs[j] in ("'", '"', "`"):
            sm = STRING_LITERAL.match(attrs, j)
            if sm:
                classes.update(sm.group(1).split())
        elif attrs[j] == "{":
            depth, k, quote = 0, j, None
            while k < len(attrs):
                c = attrs[k]
                if quote:
                    if c == quote:
                        quote = None
                elif c in ("'", '"', "`"):
                    quote = c
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            expr = attrs[j:k + 1]
            for sm in STRING_LITERAL.finditer(expr):
                classes.update(sm.group(1).split())
    return classes


def jsx_section_classes(src_dir):
    """Scan src/**/*.tsx and return {section_id: {"classes": set}}.

    Section root elements are identified by id="X"; that same id doubles as the
    in-page anchor target for <a href="#X"> nav links (no separate tracing attr).
    All three className forms are collected (literal / template / cn(...)) —
    for expressions, every string literal inside is merged in.
    """
    found = {}
    for path in sorted(Path(src_dir).rglob("*.tsx")):
        try:
            code = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for om in JSX_SECTION_OPEN.finditer(code):
            end = _jsx_tag_end(code, om.end())
            if end < 0:
                continue
            attrs = code[om.end():end]
            sid_m = JSX_SECTION_ID.search(attrs)
            if not sid_m:
                continue
            sid = sid_m.group(1)
            classes = _extract_classnames(attrs)
            entry = found.setdefault(sid, {"classes": set()})
            entry["classes"].update(classes)
    return found


def check_section_blueprint(blueprint, src_dir, report):
    """Every class in the blueprint must appear on the root element of the
    same-named React section."""
    actual = jsx_section_classes(src_dir)
    if not actual:
        report["warnings"].append(
            f"No <section id=...> found under {src_dir}——"
            "every React section root element must keep id= "
            "(it identifies the section and doubles as the nav anchor target)")
        return
    for sid, cls_str in blueprint.items():
        want = set(cls_str.split())
        if not want:
            continue
        if sid not in actual:
            report["warnings"].append(
                f'section_blueprint["{sid}"]: no matching <section id="{sid}"> found in React code'
                " (nav <a href=\"#" + sid + "\"> will jump to page top)")
            continue
        entry = actual[sid]
        missing = sorted(want - entry["classes"])
        if missing:
            report["warnings"].append(
                f'section_blueprint["{sid}"]: React root element is missing {" ".join(missing)}'
                "——top-level visual classes lost for this section (background/text/border), "
                "visual baseline mismatch")


def parse_front_matter(text):
    """Parse the YAML-like front matter block into a nested dict (top-level scalars + one-level nesting)."""
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return None
    fm, current = {}, None
    for line in m.group(1).splitlines():
        if re.match(r"^\S", line):
            key = line.split(":", 1)[0].strip()
            rest = line.split(":", 1)[1].strip() if ":" in line else ""
            if rest and not rest.startswith("#"):
                fm[key] = rest.strip().strip('"')
                current = None
            else:
                fm[key] = {}
                current = key
        elif current is not None and ":" in line:
            k, v = line.strip().split(":", 1)
            v = v.split("#", 1)[0].strip().strip('"')
            if k.strip() and v:
                fm[current][k.strip()] = v
    return fm


def hsl_to_rgb(triplet):
    """Bare 'H S% L%' triplet -> (r, g, b) floats in 0-1, or None if it doesn't parse."""
    m = HSL_TRIPLET.match(triplet)
    if not m:
        return None
    h, s, l = float(m.group(1)) / 360.0, float(m.group(2)) / 100.0, float(m.group(3)) / 100.0
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return r, g, b


def contrast_ratio(t1, t2):
    """WCAG contrast ratio between two HSL triplets, or None if either fails to parse."""
    def lum(rgb):
        def chan(c):
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = (chan(c) for c in rgb)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    c1, c2 = hsl_to_rgb(t1), hsl_to_rgb(t2)
    if c1 is None or c2 is None:
        return None
    l1, l2 = sorted((lum(c1), lum(c2)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def main():
    """CLI entry: validate DESIGN.md tokens/order/contrast, optionally against index.css and src/."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("design_md", help="DESIGN.md path")
    ap.add_argument("--index-css", help="src/index.css path (for per-variable consistency validation)")
    ap.add_argument("--src", help="src/ path (validate section_blueprint against React code)")
    args = ap.parse_args()

    report = {"ok": True, "errors": [], "warnings": []}
    design_md_arg = resolve_input_path(args.design_md)
    path = Path(design_md_arg)
    if not path.exists():
        report["errors"].append(f"File does not exist: {path}")
        _finish(report)
    text = path.read_text(encoding="utf-8")

    fm = parse_front_matter(text)
    if fm is None:
        report["errors"].append("Missing front matter (YAML header enclosed by ---)")
        _finish(report)
    tokens = fm.get("tokens") if isinstance(fm.get("tokens"), dict) else None
    if not tokens:
        report["errors"].append(
            "front matter is missing the tokens section (should be generated by "
            "apply_design_tokens.py --emit-designmd-tokens)")
        _finish(report)
    customs = fm.get("custom_tokens") if isinstance(fm.get("custom_tokens"), dict) else {}
    if "name" not in fm:
        report["warnings"].append("front matter is missing name (should match the manifest title)")

    all_tokens = {**tokens, **customs}
    for name, value in all_tokens.items():
        if name in NON_COLOR:
            if not re.match(r"^[0-9.]+(rem|px|em)$", value):
                report["errors"].append(f"--{name}: invalid length value '{value}'")
        elif not HSL_TRIPLET.match(value):
            report["errors"].append(f"--{name}: value '{value}' is not a bare HSL triplet")

    if args.index_css:
        css_path = Path(resolve_input_path(args.index_css))
        if not css_path.exists():
            report["errors"].append(f"index.css does not exist: {css_path}")
        else:
            css = css_path.read_text(encoding="utf-8")
            root_m = re.search(r":root\s*\{([^}]*)\}", css)
            css_root = dict(re.findall(r"--([a-z0-9-]+)\s*:\s*([^;]+);", root_m.group(1))) if root_m else {}
            css_root = {k: re.sub(r"\s+", " ", v.strip()) for k, v in css_root.items()}
            for name, value in all_tokens.items():
                if name.startswith("dark-"):
                    continue
                if name not in css_root:
                    report["errors"].append(
                        f"--{name}: present in DESIGN.md but not in index.css :root (injection missed?)")
                elif css_root[name] != re.sub(r"\s+", " ", value.strip()):
                    report["errors"].append(
                        f"--{name}: DESIGN.md='{value}' does not match index.css='{css_root[name]}'")

    body = text.split("---", 2)[-1]
    found = [(body.index(f"## {s}"), s) for s in SECTION_ORDER if f"## {s}" in body]
    if [s for _, s in sorted(found)] != [s for _, s in found]:
        report["errors"].append(
            f"Sections out of order: expected {' → '.join(SECTION_ORDER)} (may be omitted but not reordered)")
    if not found:
        report["warnings"].append("No standard section found in the body (Overview/Colors/…)")

    pairs = [("foreground", "background", "body text"),
             ("primary-foreground", "primary", "primary button")]
    for fg, bg, label in pairs:
        if fg in tokens and bg in tokens:
            ratio = contrast_ratio(tokens[fg], tokens[bg])
            if ratio is not None and ratio < 4.5:
                report["errors"].append(f"{label} contrast {fg}/{bg} = {ratio:.2f}:1 < 4.5:1 (WCAG AA)")

    if args.src:
        blueprint = fm.get("section_blueprint") if isinstance(fm.get("section_blueprint"), dict) else None
        src_dir = Path(resolve_input_path(args.src))
        if not src_dir.is_dir():
            report["errors"].append(f"--src path does not exist: {src_dir}")
        elif not blueprint:
            report["warnings"].append(
                "front matter is missing section_blueprint (should be extracted by apply_design_tokens.py)")
        else:
            check_section_blueprint(blueprint, src_dir, report)

    _finish(report)


def _finish(report):
    """Print the report as JSON and exit 0 on success, 1 if any error was recorded."""
    report["ok"] = not report["errors"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
