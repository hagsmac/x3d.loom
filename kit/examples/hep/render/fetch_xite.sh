#!/bin/sh
# Fetch the pinned X_ITE build into site/x_ite (not committed; see .gitignore). The stills harness serves it from 127.0.0.1.
set -e
cd "$(dirname "$0")"
VER=16.5.1
mkdir -p site/.pack
npm pack --silent "x_ite@$VER" --pack-destination site/.pack >/dev/null
tar -xzf "site/.pack/x_ite-$VER.tgz" -C site/.pack
rm -rf site/x_ite && mv site/.pack/package/dist site/x_ite && rm -rf site/.pack site/x_ite/x_ite.zip
sha256sum site/x_ite/x_ite.min.js 2>/dev/null || shasum -a 256 site/x_ite/x_ite.min.js
