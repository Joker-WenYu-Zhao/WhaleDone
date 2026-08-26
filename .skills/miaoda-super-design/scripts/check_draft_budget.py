#!/usr/bin/env python3
"""Draft-count budget interceptor -- 3 drafts in the first round, 1 per round after that.

Rule: the first round always produces 3 proposals. Every later round that produces new
drafts (iteration, a new page, "give me a few more versions") produces exactly 1 new html,
then ends the round after delivery and asks the user in the closing message whether to continue.

Usage (design_dir is tasks/design/ in debug mode):
  after P1 clarification  python3 check_draft_budget.py tasks/design --mark-clarified --reason "..."
  at the start of a round  python3 check_draft_budget.py tasks/design --begin-round
  self-check after drafts  python3 check_draft_budget.py tasks/design --check

State file: design-budget.json next to design_dir by default (tasks/design ->
tasks/design-budget.json). It only holds round-scoped state (snapshot/budget/clarified/
round_open) -- manifest.json has no notion of rounds, so the script must track that itself.
Override with --state.

Data sources `--check` uses to decide whether this round's new drafts passed, in priority order:
  1. `{design_dir}/manifest.json` exists (engineering hook environment): read drafts[].status;
     only status=="ready" (or the legacy "valid") counts as passed. The engineering side sets
     ready only after check_design_quality.py actually returned a passing JSON report, so it is
     unaffected by this command re-running the checker itself and immune to problems like a
     shell pipeline clobbering the exit code.
  2. No manifest.json and no local design-budget.json state either (--begin-round was never
     run): treat this as local debugging outside the engineering environment and fall back to
     running check_design_quality.py in a subprocess (the old behavior, kept so the script
     stays usable standalone).
  3. No manifest.json but local design-budget.json state exists (we are in the engineering
     environment, no draft write has triggered manifest registration yet): treat as 0 valid
     drafts. Not an error -- just report that nothing has passed yet.

Key edge case: the manifest only registers drafts the model actively ran
check_design_quality.py on and that passed. If the model writes a new draft but never
validates it before finishing, that draft never shows up in the manifest (not as invalid --
there is simply no entry, or it stays at generating until the end-of-round fallback marks it
invalid). `--check` must detect "new this round but missing from or not valid in the manifest"
and name the files explicitly. It must not pass just because the manifest holds enough valid
entries to cover the budget -- hitting the budget count does not prove the counted files are
this round's new ones.

sha is recorded purely as bookkeeping for the files that passed this round; the script does
not use it to detect tampering.

Exit codes: 0 = pass; 2 = over budget / blocked by quality check; 1 = usage or state error.
Pure Python standard library, no third-party dependencies.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys


APP_ROOT_RE = re.compile(r"^app-[\w-]+$")

MANIFEST_FILENAME = "manifest.json"
STATUS_VALID = "ready"
# Read-side compat with manifests written before the engineering rename (valid/invalid -> ready/failed)
_STATUS_VALID_ALIASES = {STATUS_VALID, "valid"}


def _walk_up_for_app(start):
    """Walk up from `start` to the first `app-<id>` directory; return None if none found."""
    probe = os.path.abspath(start)
    while True:
        if APP_ROOT_RE.match(os.path.basename(probe)):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent


def find_app_root():
    """Locate the current app root `app-<id>`: check CWD's ancestors first, then the script's own location.

    Kept in sync with new_draft.py (both scripts must resolve the same app root; otherwise
    one writes state to `/workspace/app-x/tasks/design-budget.json` while the other looks for
    it at `/workspace/tasks/design-budget.json` and they never see each other). CWD is
    unreliable -- the engineering side may run bash from the app's parent directory (e.g.
    `/workspace`), where `app-<id>` is a child of CWD and walking up cannot reach it. The
    script is deployed under `<app-root>/.skills/.../scripts/`, so `__file__`'s ancestry
    always contains `app-<id>` -- a more stable anchor than CWD.
    """
    hit = _walk_up_for_app(os.getcwd())
    if hit:
        return hit
    hit = _walk_up_for_app(os.path.dirname(os.path.abspath(__file__)))
    if hit:
        return hit
    return os.path.abspath(os.getcwd())


def resolve_design_dir(arg):
    """Resolve design_dir to an absolute path: relative paths against the app root, absolute as-is."""
    if os.path.isabs(arg):
        return os.path.abspath(arg)
    return os.path.join(find_app_root(), arg)


def html_set(design_dir):
    """Sorted basenames of every *.html file directly inside design_dir."""
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(design_dir, "*.html")))


def sha256_of(path):
    """Stable sha256 (reads the whole file; drafts are small, no need to chunk). Returns None if the file is missing."""
    if not os.path.isfile(path):
        return None
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _snapshot_sha(design_dir, files):
    """Compute a sha snapshot for the current file set (bookkeeping only, not used for tampering detection)."""
    return {f: sha256_of(os.path.join(design_dir, f)) for f in files}


def default_state_path(design_dir):
    """State file path: a design-budget.json sibling of design_dir."""
    parent = os.path.dirname(os.path.abspath(design_dir.rstrip("/")))
    return os.path.join(parent, "design-budget.json")


def load_state(state_file):
    """Read the state file; on corruption return an empty dict and warn (no traceback)."""
    if not os.path.isfile(state_file):
        return {}
    try:
        with open(state_file, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARN: state file corrupted ({state_file}): {e}. Treating as empty state.", file=sys.stderr)
        return {}


def save_state(state_file, state):
    """Write the state file; skip makedirs when the directory part is empty (bare filename)."""
    parent = os.path.dirname(state_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def manifest_path(design_dir):
    """Path of the engineering-written manifest.json inside design_dir."""
    return os.path.join(design_dir, MANIFEST_FILENAME)


def load_manifest(design_dir):
    """Read manifest.json; return None if absent (distinguishing "file missing" from "present but no drafts").

    The manifest is written exclusively by the engineering side (the model only reads it); this
    script only reads, never writes. On a malformed file, treat it as "unreadable" (return None)
    -- no traceback, no repair attempt.
    """
    path = manifest_path(design_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARN: manifest.json corrupted ({path}): {e}. Treating as unavailable.", file=sys.stderr)
        return None
    if not isinstance(data, dict) or "drafts" not in data:
        return None
    return data


def manifest_valid_filenames(manifest):
    """Set of filenames whose manifest status is ready (or legacy valid) (basename of path)."""
    out = set()
    for entry in manifest.get("drafts") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") not in _STATUS_VALID_ALIASES:
            continue
        path = str(entry.get("path") or "")
        if path:
            out.add(path.rsplit("/", 1)[-1])
    return out


def main():
    """CLI entry: dispatch --mark-clarified / --begin-round / --check."""
    ap = argparse.ArgumentParser(description="Draft count budget interceptor")
    ap.add_argument("design_dir", help="Draft directory (tasks/design/ in debug mode)")
    ap.add_argument("--begin-round", action="store_true",
                    help="Start this round: snapshot existing drafts and print the budget")
    ap.add_argument("--check", action="store_true",
                    help="After producing drafts, verify this round's new count against the budget")
    ap.add_argument("--mark-clarified", action="store_true",
                    help="Mark P1 clarification done (must be called before the first round's --begin-round)")
    ap.add_argument("--reason", default=None, help="Clarification reason (required with --mark-clarified)")
    ap.add_argument("--state", default=None, help="State file path (defaults to design-budget.json next to design_dir)")
    args = ap.parse_args()

    # Mutual exclusion: exactly one of --begin-round / --check / --mark-clarified
    selected = sum([args.begin_round, args.check, args.mark_clarified])
    if selected != 1:
        print("ERROR: choose exactly one of --begin-round / --check / --mark-clarified", file=sys.stderr)
        return 1
    if args.mark_clarified and not args.reason:
        print("ERROR: --mark-clarified requires --reason", file=sys.stderr)
        return 1

    design_dir = resolve_design_dir(args.design_dir)
    if not os.path.isdir(design_dir):
        os.makedirs(design_dir, exist_ok=True)
    state_file = args.state or default_state_path(design_dir)
    current = html_set(design_dir)

    if args.mark_clarified:
        state = load_state(state_file)
        state["clarified"] = True
        state["clarify_reason"] = args.reason
        save_state(state_file, state)
        print(f"Clarification marked: {args.reason}")
        return 0

    if args.begin_round:
        # Ratchet: block re-opening a new baseline while the previous round has unchecked new drafts
        prev = load_state(state_file)
        if prev:
            baseline = set(prev.get("checked") if prev.get("checked") is not None else prev.get("snapshot", []))
            strays = [p for p in current if p not in baseline]
            if strays:
                print(f"BLOCKED: found new drafts that never passed --check: {', '.join(strays)}.")
                print("The previous round's output was not validated (or over budget and not cleaned "
                      "up). Cannot open a new round directly:")
                print("  1) If over budget: keep only 1 new draft, delete the rest;")
                print(f"  2) Run python3 check_draft_budget.py {design_dir} --check and pass, "
                      "then --begin-round.")
                return 2
        # First-round detection: empty dir -> first round; existing snapshot matching current -> could
        # also be a re-begin-round after clarify. Priority: if we had a prior round, it's not the first.
        had_prior_round = "snapshot" in prev
        budget = 1 if (current or had_prior_round) else 3
        # First round (budget==3) requires P1 clarification (--mark-clarified) beforehand
        if budget == 3 and not prev.get("clarified"):
            print(
                "BLOCKED: P1 clarification not done. First send ask_user (or confirm the user already "
                "gave a color-scheme answer), then call --mark-clarified --reason '<reason>' and rerun --begin-round."
            )
            return 2
        new_state = dict(prev)
        new_state.update({
            "snapshot": current,
            "budget": budget,
            "checked": current,
            "round_open": True,
        })
        save_state(state_file, new_state)
        if budget == 3:
            print("This round budget: 3 drafts (the first round; the three layout skeletons must differ).")
        else:
            print(f"{len(current)} draft(s) already exist. This round budget: 1 draft -- build only one "
                  "html, end this round normally after delivery, and ask the user whether to continue "
                  "in the closing message.")
        return 0

    # --check
    state = load_state(state_file)
    # Note: first-round snapshot is an empty list (the dir was empty), so truthiness cannot be
    # used -- must check whether the key exists at all.
    if "snapshot" not in state:
        budget = 3 if len(current) <= 3 else 1
        print("WARN: no snapshot for this round found; cannot precisely determine this round's new count.")
        print("Run --begin-round at the start of each round. Reminding by total for now: ", end="")
        print("Within 3 drafts for the first round." if budget == 3
              else f"{len(current)} draft(s) already exist; non-first rounds allow only 1 draft per round.")
        return 0
    snapshot, budget = set(state.get("snapshot", [])), int(state.get("budget", 1))
    new = [p for p in current if p not in snapshot]
    n = len(new)

    if not new:
        # No new draft this round -- do not close round_open (might still be drafting, just a mid-check)
        state["checked"] = current
        state["sha"] = _snapshot_sha(design_dir, current)
        save_state(state_file, state)
        print("No new draft added this round yet.")
        return 0

    # Determine whether this round's new drafts have passed -- if manifest.json exists, read it
    # (the engineering side's authoritative registry; see data-source priority in the module
    # docstring). If absent, distinguish between "local debugging outside the engineering env"
    # and "engineering env but no draft has triggered manifest registration yet"; only the former
    # falls back to running check_design_quality.py as a subprocess.
    manifest = load_manifest(design_dir)
    if manifest is not None:
        valid_names = manifest_valid_filenames(manifest)
        not_yet_valid = [f for f in new if f not in valid_names]
        if not_yet_valid:
            print(f"BLOCKED: {len(not_yet_valid)} of this round's new drafts did not pass check_design_quality.py"
                  f" (not registered as valid in manifest.json): {', '.join(not_yet_valid)}.")
            print("First run on these files:")
            print(f"  python3 check_design_quality.py {' '.join(os.path.join(design_dir, f) for f in not_yet_valid)}")
            print("Confirm exit 0, then rerun this command -- enough valid entries in manifest to meet "
                  "budget does not mean these specific files passed; each must map to this round's new filenames.")
            return 2
        passed = new
    elif "snapshot" not in state or state.get("_never_begun"):
        # Should not reach here in practice (snapshot existence was checked above); kept as a defensive guard
        passed = new
    else:
        # manifest absent: use whether --begin-round has been run to distinguish scenarios.
        # design-budget.json state exists (we got this far, so snapshot must exist) means we are
        # in the engineering env but no draft write has triggered manifest registration yet -- not
        # an error, but we also cannot assume "no manifest = all passed". Fall back conservatively
        # to running the checker locally (preserves standalone usability).
        quality = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_design_quality.py")
        if not os.path.isfile(quality):
            print("WARN: manifest.json not found and check_design_quality.py not found; cannot determine "
                  "whether this round's new drafts passed, treating as not passed.")
            return 2
        files = [os.path.join(design_dir, f) for f in new]
        res = subprocess.run([sys.executable, quality, *files], capture_output=True, text=True)
        if res.returncode != 0:
            print("BLOCKED: this round's new drafts did not pass check_design_quality (error level).")
            print("First run:")
            print(f"  python3 check_design_quality.py {' '.join(files)}")
            print("Fix via str_replace_editor per the output, then rerun this command after it passes.")
            for line in (res.stdout or "").splitlines()[:20]:
                print("  ", line)
            return 2
        passed = new

    n = len(passed)
    if n <= budget:
        state["checked"] = current
        state["sha"] = _snapshot_sha(design_dir, current)
        # Only close the round when the budget is used up (n == budget); if not full yet keep round_open
        if n == budget:
            state["round_open"] = False
        save_state(state_file, state)
        if budget == 1:
            print(f"OK: 1 new draft this round ({passed[0]}), budget used up, end this round after delivery.")
        else:
            if n == budget:
                print(f"OK: the first round has all {n}/3 drafts ({', '.join(passed)}), end this round after delivery.")
            else:
                print(f"OK: the first round now has {n}/3 drafts ({', '.join(passed)}), keep filling the rest.")
        return 0
    print(f"BLOCKED: this round budget is {budget} draft(s), but {n} were added ({', '.join(passed)}).")
    print("Rule: exactly 3 proposals in the first round; only 1 html per round afterward.")
    print("Fix: keep only 1 new draft to deliver, delete the rest of this round's new files (not yet "
          "registered, safe to delete); after deleting you must rerun --check and pass (otherwise the next "
          "round's --begin-round will be BLOCKED).")
    return 2


if __name__ == "__main__":
    sys.exit(main())
