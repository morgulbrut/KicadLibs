#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

TAG="${1:?Usage: make-release.sh <version-or-tag> [kicad_version]}"
KICAD_VERSION="${2:-9.0.0}"

./validate.sh
python3 scripts/build_package.py "$TAG" --kicad-version "$KICAD_VERSION"
