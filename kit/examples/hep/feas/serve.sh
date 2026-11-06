#!/bin/sh
# Serve feas/site on 127.0.0.1:8765 (python stdlib http.server; no-cache not needed for static).
cd "$(dirname "$0")/site" && exec python3 -m http.server 8765 --bind 127.0.0.1
