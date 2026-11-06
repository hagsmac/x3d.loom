#!/usr/bin/env bash
# Look v3 witness run: build three committed Pythia 8 fixtures with --look v3 (and their bloom wrappers), run the
# hep-event and traps witnesses on the scenes, and hash what was built. If the run folder already holds scenes.sha256,
# the fresh build must match it byte for byte (the builder is deterministic), so the committed hashes are checked.
set -euo pipefail
V1="$(cd "$(dirname "$0")/../.." && pwd)"
HEP="$V1/kit/examples/hep"; LOOM="$V1/kit/loom"
RUN="${1:-$V1/runs/hep-demo-v3-$(date -u +%Y%m%d)}"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/cand/events-v3" "$RUN/evidence"
cp "$HEP/hep-demo-spec.json" "$WORK/cand/"
for s in pythia-dijet-hero pythia-zmumu pythia-qcd-demo; do
  python3 -I "$HEP/build_event_scene.py" "$HEP/fixtures/$s.event.json" "$WORK/cand/events-v3" --look v3 --bloom > /dev/null
done
"$LOOM" hepevent "$WORK/cand" --evidence "$RUN/evidence" --events 'events-v3/*.event.json' --spec "$WORK/cand/hep-demo-spec.json" > /dev/null
"$LOOM" traps "$WORK/cand" --evidence "$RUN/evidence" --files 'events-v3/*.x3d' --host strict > /dev/null
python3 -I -c "import json,sys; [print(n, json.load(open(sys.argv[1]+'/'+n+'.json'))['status']) for n in ('hep-event','traps')]" "$RUN/evidence"
(cd "$WORK/cand/events-v3" && sha256sum *.x3d) > "$WORK/scenes.sha256"
if [ -f "$RUN/scenes.sha256" ]; then diff "$RUN/scenes.sha256" "$WORK/scenes.sha256" && echo "scenes match the committed hashes"; else cp "$WORK/scenes.sha256" "$RUN/scenes.sha256"; fi
