#!/bin/sh
# Fetch the pinned X_ITE build into vendor/x_ite (not committed). Without it, index.html falls back to the CDN.
set -e
cd "$(dirname "$0")/.."
VER=16.5.1
mkdir -p vendor/.pack
npm pack "x_ite@$VER" --pack-destination vendor/.pack >/dev/null
tar -xzf "vendor/.pack/x_ite-$VER.tgz" -C vendor/.pack
rm -rf vendor/x_ite && mv vendor/.pack/package/dist vendor/x_ite && rm -rf vendor/.pack
sha256sum vendor/x_ite/x_ite.min.js 2>/dev/null || shasum -a 256 vendor/x_ite/x_ite.min.js
