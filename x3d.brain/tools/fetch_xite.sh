#!/bin/sh
# Fetch the pinned X_ITE build into page/vendor/x_ite (not committed: page/.gitignore lists vendor/).
# Without it the page falls back to the same version from a public CDN (a network request).
# Needs node and npm. Prints the sha256 of the min build. Run once, then serve the page folder:  python3 -m http.server -d page 8000
set -e
cd "$(dirname "$0")/.."
VER=16.6.0
OUT=page/vendor/x_ite
mkdir -p page/vendor/.pack
npm pack "x_ite@$VER" --pack-destination page/vendor/.pack >/dev/null
tar -xzf "page/vendor/.pack/x_ite-$VER.tgz" -C page/vendor/.pack
rm -rf "$OUT" && mkdir -p "$OUT"
D=page/vendor/.pack/package/dist
cp "$D/x_ite.min.js" "$D/x_ite.css" "$D/LICENSE.md" "$OUT/"
# assets: everything except the unminified components (the page loads the .min.js ones)
(cd "$D" && find assets -type f ! \( -path 'assets/components/*' ! -name '*.min.js' \)) | while read -r f; do
  mkdir -p "$OUT/$(dirname "$f")" && cp "$D/$f" "$OUT/$f"
done
rm -rf page/vendor/.pack
sha256sum "$OUT/x_ite.min.js" 2>/dev/null || shasum -a 256 "$OUT/x_ite.min.js"
