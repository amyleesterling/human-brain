#!/usr/bin/env bash
# Draco-compress every mesh in a directory in place.
#
# Run this LAST. scripts/build_data.py reads the layer meshes with trimesh to
# work out the pial surface, and it wants them uncompressed. The order is
# fetch_h01.py, then build_data.py, then this.
#
# q14 position quantisation is topology lossless at these scales: the meshes
# here are a few thousand micrometres across, so 2^14 steps put the grid at
# roughly 0.2 um, well under a single voxel of the source segmentation.
set -euo pipefail
dir="${1:?usage: draco.sh <dir>}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
before=0; after=0
for f in "$dir"/*.glb; do
  b=$(stat -c%s "$f")
  npx --yes @gltf-transform/cli@latest draco "$f" "$tmp/out.glb" \
      --quantize-position 14 >/dev/null 2>&1
  mv "$tmp/out.glb" "$f"
  a=$(stat -c%s "$f")
  before=$((before+b)); after=$((after+a))
  printf '  %-28s %7.0f kB -> %7.0f kB\n' "$(basename "$f")" "$((b/1000))" "$((a/1000))"
done
awk -v b="$before" -v a="$after" 'BEGIN{
  printf "total %.1f MB -> %.1f MB (%.1fx)\n", b/1e6, a/1e6, (a?b/a:0)
}'
