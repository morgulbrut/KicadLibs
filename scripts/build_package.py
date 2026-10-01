#!/usr/bin/env python3
"""Build a KiCad PCM release package.

Stages a copy of src/ (so the real working tree is never modified), rewrites
3D model paths in that copy to their canonical PCM form, zips it into a PCM
"library" package, and updates metadata.json, packages.json, repository.json
and resources.zip at the repo root so they can be committed back to main as
the self-hosted PCM repository.

Usage: build_package.py <version-or-tag> [--kicad-version X.Y.Z] [--status stable]
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
import fix_3d_paths  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
RESOURCES = REPO_ROOT / "resources"
BUILD_DIR = REPO_ROOT / "build"
STAGE_DIR = BUILD_DIR / "stage"
METADATA_PATH = REPO_ROOT / "metadata.json"
PACKAGES_PATH = REPO_ROOT / "packages.json"
REPOSITORY_PATH = REPO_ROOT / "repository.json"
RESOURCES_ZIP_PATH = REPO_ROOT / "resources.zip"

ZIP_FILE_NAME = "kicadlibs.zip"
PLACEHOLDER = "<github-owner>"
VERSION_RE = re.compile(r"^\d{1,4}(\.\d{1,4}(\.\d{1,6})?)?$")
GITHUB_HOMEPAGE_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+?)/?$")


def load_metadata() -> dict:
    return json.loads(METADATA_PATH.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def github_owner_repo(metadata: dict) -> Tuple[str, str]:
    homepage = metadata.get("resources", {}).get("homepage", "")
    match = GITHUB_HOMEPAGE_RE.match(homepage)
    if not match:
        sys.exit(
            "ERROR: metadata.json resources.homepage must be a GitHub repo URL "
            f"(https://github.com/<owner>/<repo>), got: {homepage!r}"
        )
    return match.group(1), match.group(2)


def stage_sources() -> None:
    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True)
    shutil.copytree(SRC / "symbols", STAGE_DIR / "symbols")
    shutil.copytree(SRC / "footprints", STAGE_DIR / "footprints")
    shutil.copytree(SRC / "3dmodels", STAGE_DIR / "3dmodels")
    if RESOURCES.is_dir() and any(RESOURCES.iterdir()):
        shutil.copytree(RESOURCES, STAGE_DIR / "resources")


def zip_directory(zip_handle: zipfile.ZipFile, directory: Path, arc_prefix: str) -> None:
    for file_path in sorted(directory.rglob("*")):
        if file_path.is_file() and file_path.name != ".gitkeep":
            zip_handle.write(file_path, f"{arc_prefix}/{file_path.relative_to(directory)}")


def build_zip(version: str, kicad_version: str, status: str, template: dict) -> Path:
    BUILD_DIR.mkdir(exist_ok=True)
    zip_path = BUILD_DIR / ZIP_FILE_NAME
    if zip_path.exists():
        zip_path.unlink()

    internal_metadata = dict(template)
    internal_metadata["versions"] = [{"version": version, "status": status, "kicad_version": kicad_version}]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_handle:
        for name in ("symbols", "footprints", "3dmodels", "resources"):
            directory = STAGE_DIR / name
            if directory.is_dir():
                zip_directory(zip_handle, directory, name)
        zip_handle.writestr("metadata.json", json.dumps(internal_metadata, indent=4))

    return zip_path


def install_size(zip_path: Path) -> int:
    with zipfile.ZipFile(zip_path) as zip_handle:
        return sum(entry.file_size for entry in zip_handle.infolist() if not entry.is_dir())


def build_resources_zip() -> Optional[Path]:
    resources_stage = STAGE_DIR / "resources"
    if not resources_stage.is_dir() or not any(resources_stage.iterdir()):
        print("WARNING: resources/ has no files (no icon.png) - skipping resources.zip")
        return None
    if RESOURCES_ZIP_PATH.exists():
        RESOURCES_ZIP_PATH.unlink()
    with zipfile.ZipFile(RESOURCES_ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zip_handle:
        zip_directory(zip_handle, resources_stage, "resources")
    return RESOURCES_ZIP_PATH


def utc_now() -> Tuple[int, str]:
    now = time.time()
    return int(now), time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now))


def update_metadata(
    template: dict, version: str, status: str, kicad_version: str,
    zip_sha256: str, zip_size: int, zip_install_size: int, download_url: str,
) -> dict:
    existing_versions = template.get("versions", [])
    if any(v["version"] == version for v in existing_versions):
        sys.exit(f"ERROR: version {version} already exists in metadata.json")

    new_version = {
        "version": version,
        "status": status,
        "kicad_version": kicad_version,
        "download_sha256": zip_sha256,
        "download_size": zip_size,
        "download_url": download_url,
        "install_size": zip_install_size,
    }
    updated = dict(template)
    updated["versions"] = [new_version] + existing_versions
    return updated


def build_repository_json(
    metadata: dict, owner: str, repo: str, packages_sha256: str, resources_zip: Optional[Path],
) -> dict:
    timestamp, time_utc = utc_now()
    repository = {
        "$schema": "https://go.kicad.org/pcm/schemas/v1#/definitions/Repository",
        "name": f"{metadata['name']} PCM repository",
        "maintainer": metadata.get("maintainer", metadata["author"]),
        "packages": {
            "url": f"https://raw.githubusercontent.com/{owner}/{repo}/main/packages.json",
            "sha256": packages_sha256,
            "update_timestamp": timestamp,
            "update_time_utc": time_utc,
        },
    }
    if resources_zip is not None:
        repository["resources"] = {
            "url": f"https://raw.githubusercontent.com/{owner}/{repo}/main/resources.zip",
            "sha256": sha256_file(resources_zip),
            "update_timestamp": timestamp,
            "update_time_utc": time_utc,
        }
    return repository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="release tag or version, e.g. v1.2.3 or 1.2.3")
    parser.add_argument("--kicad-version", default="9.0.0", help="minimum supported KiCad version")
    parser.add_argument("--status", default="stable", choices=["stable", "testing", "development", "deprecated"])
    args = parser.parse_args()

    raw_tag = args.version
    version = re.sub(r"^[vV](?=\d)", "", raw_tag)
    if not VERSION_RE.match(version):
        sys.exit(f"ERROR: version must look like major[.minor[.patch]], got: {version!r}")

    template = load_metadata()
    if PLACEHOLDER in json.dumps(template):
        sys.exit(
            f"ERROR: metadata.json still contains the '{PLACEHOLDER}' placeholder. "
            "Fill in the real GitHub owner/org before releasing."
        )

    owner, repo = github_owner_repo(template)

    print("Staging source files...")
    stage_sources()

    print("Normalizing 3D model paths for PCM...")
    if not fix_3d_paths.fix(STAGE_DIR, template["identifier"]):
        sys.exit("ERROR: one or more 3D model references could not be resolved; aborting build")

    print(f"Building {ZIP_FILE_NAME}...")
    zip_path = build_zip(version, args.kicad_version, args.status, template)
    zip_sha256 = sha256_file(zip_path)
    zip_size = zip_path.stat().st_size
    zip_install_size = install_size(zip_path)

    download_url = f"https://github.com/{owner}/{repo}/releases/download/{raw_tag}/{ZIP_FILE_NAME}"

    print("Updating metadata.json...")
    metadata = update_metadata(
        template, version, args.status, args.kicad_version,
        zip_sha256, zip_size, zip_install_size, download_url,
    )
    write_json(METADATA_PATH, metadata)

    print("Updating packages.json...")
    packages = {"packages": [metadata]}
    write_json(PACKAGES_PATH, packages)
    packages_sha256 = sha256_file(PACKAGES_PATH)

    print("Updating resources.zip...")
    resources_zip = build_resources_zip()

    print("Updating repository.json...")
    repository = build_repository_json(metadata, owner, repo, packages_sha256, resources_zip)
    write_json(REPOSITORY_PATH, repository)

    print(f"\nDone. Package: {zip_path} ({zip_size} bytes, sha256={zip_sha256})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
