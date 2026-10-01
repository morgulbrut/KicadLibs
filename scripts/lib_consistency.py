#!/usr/bin/env python3
"""Validate repo-wide KiCad library structure and metadata.json before packaging.

Run via ./validate.sh. Fails (non-zero exit) on real problems: mismatched
category directories, corrupt .kicad_sym/.kicad_mod files, missing required
metadata.json fields, or a .kicad_mod referencing a 3D model file that does
not exist. A metadata.json that still contains the <github-owner> placeholder
only warns here (it is a hard error at release time, in build_package.py).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fix_3d_paths  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
METADATA_PATH = REPO_ROOT / "metadata.json"
PLACEHOLDER = "<github-owner>"

REQUIRED_METADATA_FIELDS = ["name", "description", "description_full", "identifier", "type", "author", "license"]
IDENTIFIER_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


def check_categories() -> bool:
    ok = True
    symbols = {p.stem for p in (SRC / "symbols").glob("*.kicad_sym")}
    footprints = {p.name[: -len(".pretty")] for p in (SRC / "footprints").glob("*.pretty")}
    models = {p.name[: -len(".3dshapes")] for p in (SRC / "3dmodels").glob("*.3dshapes")}
    for category in sorted(symbols | footprints | models):
        missing = [
            kind
            for kind, present in (
                ("symbols", category in symbols),
                ("footprints", category in footprints),
                ("3dmodels", category in models),
            )
            if not present
        ]
        if missing:
            print(f"ERROR: category '{category}' is missing: {', '.join(missing)}", file=sys.stderr)
            ok = False
    return ok


def check_balanced_parens(path: Path, required_head: str) -> bool:
    text = path.read_text(encoding="utf-8")
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                print(f"ERROR: {path}: unbalanced parentheses", file=sys.stderr)
                return False
    if depth != 0:
        print(f"ERROR: {path}: unbalanced parentheses", file=sys.stderr)
        return False
    if not text.lstrip().startswith(required_head):
        print(f"ERROR: {path}: expected to start with '{required_head}'", file=sys.stderr)
        return False
    return True


def check_kicad_files() -> bool:
    ok = True
    for sym_file in (SRC / "symbols").glob("*.kicad_sym"):
        ok = check_balanced_parens(sym_file, "(kicad_symbol_lib") and ok
    for mod_file in (SRC / "footprints").glob("*.pretty/*.kicad_mod"):
        ok = check_balanced_parens(mod_file, "(footprint") and ok
    return ok


def load_metadata() -> dict:
    if not METADATA_PATH.is_file():
        print(f"ERROR: {METADATA_PATH} not found", file=sys.stderr)
        sys.exit(1)
    return json.loads(METADATA_PATH.read_text(encoding="utf-8"))


def check_metadata(metadata: dict) -> bool:
    ok = True
    for field in REQUIRED_METADATA_FIELDS:
        if not metadata.get(field):
            print(f"ERROR: metadata.json missing required field '{field}'", file=sys.stderr)
            ok = False

    description = metadata.get("description", "")
    if len(description) > 150:
        print(f"ERROR: metadata.json 'description' is {len(description)} chars, must be <= 150", file=sys.stderr)
        ok = False

    identifier = metadata.get("identifier", "")
    if identifier and PLACEHOLDER not in identifier and not IDENTIFIER_RE.match(identifier):
        print(f"ERROR: metadata.json 'identifier' doesn't look like reverse-DNS: {identifier!r}", file=sys.stderr)
        ok = False

    if metadata.get("type") != "library":
        print(f"ERROR: metadata.json 'type' must be 'library' (got {metadata.get('type')!r})", file=sys.stderr)
        ok = False

    if PLACEHOLDER in json.dumps(metadata):
        print(
            f"WARNING: metadata.json still contains the '{PLACEHOLDER}' placeholder; "
            "fill in the real GitHub owner before creating a release"
        )

    return ok


def main() -> int:
    ok = True
    ok = check_categories() and ok
    ok = check_kicad_files() and ok

    metadata = load_metadata()
    ok = check_metadata(metadata) and ok
    ok = fix_3d_paths.check(SRC, metadata.get("identifier", "")) and ok

    if ok:
        print("validate: OK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
