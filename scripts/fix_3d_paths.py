#!/usr/bin/env python3
"""Check or fix 3D model paths inside .kicad_mod footprint files for PCM packaging.

KiCad's footprint editor writes whatever path resolves on the local machine
(an absolute path, or a ${KIPRJMOD}-relative one). None of that works once the
library is installed by someone else through KiCad's Plugin & Content Manager.
PCM instead resolves 3D models of packages it installed through the
${KICADn_3RD_PARTY} environment variable. KICAD6_3RD_PARTY (the oldest,
introduced in KiCad 6.0 together with PCM itself) is used deliberately here,
since it is the version KiCad's variable-resolution code treats as the
backward-compatible base that newer KiCad versions fall back to.
"""
import argparse
import re
import sys
from pathlib import Path

MODEL_RE = re.compile(r'(\(model\s+")([^"]*)(")')
THIRD_PARTY_VAR = "KICAD6_3RD_PARTY"


def canonical_path(identifier: str, category: str, basename: str) -> str:
    identifier_us = identifier.replace(".", "_")
    return f"${{{THIRD_PARTY_VAR}}}/3dmodels/{identifier_us}/{category}.3dshapes/{basename}"


def model_basename(model_path: str) -> str:
    return model_path.replace("\\", "/").rsplit("/", 1)[-1]


def _iter_mod_files(root: Path):
    footprints_dir = root / "footprints"
    if not footprints_dir.is_dir():
        return
    for pretty_dir in sorted(footprints_dir.glob("*.pretty")):
        category = pretty_dir.name[: -len(".pretty")]
        for mod_file in sorted(pretty_dir.glob("*.kicad_mod")):
            yield category, mod_file


def check(root: Path, identifier: str) -> bool:
    """Report path status. Returns False if a referenced 3D model file is missing."""
    ok = True
    for category, mod_file in _iter_mod_files(root):
        text = mod_file.read_text(encoding="utf-8")
        for match in MODEL_RE.finditer(text):
            basename = model_basename(match.group(2))
            model_file = root / "3dmodels" / f"{category}.3dshapes" / basename
            if not basename or not model_file.is_file():
                print(
                    f"ERROR: {mod_file}: references missing 3D model "
                    f"'{basename}' (expected at {model_file})",
                    file=sys.stderr,
                )
                ok = False
                continue
            expected = canonical_path(identifier, category, basename)
            if match.group(2) != expected:
                print(
                    f"INFO: {mod_file}: local path will be rewritten at release time\n"
                    f"      from: {match.group(2)}\n"
                    f"      to:   {expected}"
                )
    return ok


def fix(root: Path, identifier: str) -> bool:
    """Rewrite every (model "...") path to its canonical PCM form in place.

    Returns False (and leaves the offending reference untouched) if a 3D
    model file it points at cannot be found, so the caller can abort the
    build instead of shipping a dangling reference.
    """
    ok = True

    for category, mod_file in _iter_mod_files(root):
        text = mod_file.read_text(encoding="utf-8")

        def replace(match: "re.Match[str]") -> str:
            nonlocal ok
            basename = model_basename(match.group(2))
            model_file = root / "3dmodels" / f"{category}.3dshapes" / basename
            if not basename or not model_file.is_file():
                print(
                    f"ERROR: {mod_file}: references missing 3D model "
                    f"'{basename}' (expected at {model_file})",
                    file=sys.stderr,
                )
                ok = False
                return match.group(0)
            return match.group(1) + canonical_path(identifier, category, basename) + match.group(3)

        new_text = MODEL_RE.sub(replace, text)
        if new_text != text:
            mod_file.write_text(new_text, encoding="utf-8")

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", required=True, type=Path,
        help="directory containing footprints/ and 3dmodels/ (e.g. src, or a staged build copy)",
    )
    parser.add_argument("--identifier", required=True, help="PCM package identifier, e.g. com.github.owner.repo")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report issues without modifying files")
    mode.add_argument("--fix", action="store_true", help="rewrite 3D model paths in place to canonical PCM form")
    args = parser.parse_args()

    ok = check(args.root, args.identifier) if args.check else fix(args.root, args.identifier)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
