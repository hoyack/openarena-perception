#!/usr/bin/env bash
# Extract AAS and BSP files from OpenArena's pk3 archives into maps/.
#
# OpenArena ships maps inside pk3 (ZIP) files at the game's basepath.
# This script extracts the ones our tests and tools reference so we
# don't duplicate game assets in the repo.
#
# Usage:
#   ./scripts/extract_maps.sh
#   ./scripts/extract_maps.sh /path/to/openarena/baseoa
#
# Default search paths (in order):
#   1. $OA_BASEPATH (env var)
#   2. /usr/lib/openarena/baseoa
#   3. /usr/share/games/openarena/baseoa
#   4. ~/.openarena/baseoa

set -euo pipefail

MAPS_DIR="$(cd "$(dirname "$0")/.." && pwd)/maps"
MAPS=(oa_dm1 oa_dm2 oa_rpg3dm2)
EXTENSIONS=(aas bsp)

# Resolve basepath
if [[ -n "${1:-}" ]]; then
    BASEPATH="$1"
elif [[ -n "${OA_BASEPATH:-}" ]]; then
    BASEPATH="$OA_BASEPATH"
else
    for candidate in \
        /usr/lib/openarena/baseoa \
        /usr/share/games/openarena/baseoa \
        "$HOME/.openarena/baseoa"; do
        if [[ -d "$candidate" ]]; then
            BASEPATH="$candidate"
            break
        fi
    done
fi

if [[ -z "${BASEPATH:-}" ]]; then
    echo "ERROR: Could not find OpenArena baseoa directory."
    echo "Set OA_BASEPATH or pass the path as an argument."
    exit 1
fi

echo "OpenArena basepath: $BASEPATH"
mkdir -p "$MAPS_DIR"

extracted=0
skipped=0

for map in "${MAPS[@]}"; do
    for ext in "${EXTENSIONS[@]}"; do
        target="$MAPS_DIR/${map}.${ext}"
        if [[ -f "$target" ]]; then
            echo "  SKIP  ${map}.${ext} (already exists)"
            skipped=$((skipped + 1))
            continue
        fi
        # Search pk3 archives for the file
        found=false
        for pk3 in "$BASEPATH"/*.pk3; do
            [[ -f "$pk3" ]] || continue
            if unzip -l "$pk3" 2>/dev/null | grep -q "maps/${map}.${ext}"; then
                unzip -o -j "$pk3" "maps/${map}.${ext}" -d "$MAPS_DIR" >/dev/null 2>&1
                if [[ -f "$target" ]]; then
                    echo "  OK    ${map}.${ext} <- $(basename "$pk3")"
                    extracted=$((extracted + 1))
                    found=true
                    break
                fi
            fi
        done
        if ! $found; then
            echo "  MISS  ${map}.${ext} (not found in any pk3)"
        fi
    done
done

echo ""
echo "Done: $extracted extracted, $skipped already present in $MAPS_DIR"
