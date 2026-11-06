#!/bin/sh
# P1 Site scenes of the zinc finger study: one X3D world per deposited structure, judged by four witnesses.
# 1. copy the pinned archive files from the P1 structures run, re-verify every pin, write the specs;
# 2. build one scene per structure (model 1, drawn by the rule in zinc_site_scene.py);
# 3. grammar and meaning (the x3d_mcp fork at the family pin), traps, and an independent data-true reader;
# 4. nine negative controls on the data-true reader (each must fail with its own code), then accept and a receipt.
# The eyes record is written after the renders are read (graded S); rerun the receipt step then.
# Usage: kit/examples/run_zinc_scenes.sh RUN_DIR [STRUCTURES_CANDIDATE]. Needs a python3 with MDAnalysis on PATH
# and the fork checkout at ~/Projects/x3d/x3d_mcp (or LOOM_FORK).
set -eu
V1="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="${1:-$V1/runs/zinc-scenes-$(date -u +%Y%m%d)}"
SRC="${2:-$V1/runs/zinc-structures-20261106/candidate}"
CAND="$RUN/candidate"
EV="$RUN/evidence"
LOOM="$V1/kit/loom"

rm -rf "$EV" "$CAND"; mkdir -p "$EV" "$CAND/scenes"
cp -r "$SRC/structures" "$CAND/"
IDS="$(python3 -I "$V1/kit/examples/zinc_structures.py" "$CAND")"
cp "$V1/kit/examples/zinc_scene_truth.py" "$CAND/scene_truth.py"
for id in $IDS; do
  python3 -I "$V1/kit/examples/zinc_site_scene.py" "$CAND" "$id" "$CAND/scenes/$id.x3d"
done
"$LOOM" candidate "$CAND"

"$LOOM" grammar "$CAND" --evidence "$EV" --files 'scenes/*.x3d' > /dev/null
"$LOOM" traps "$CAND" --evidence "$EV" --files 'scenes/*.x3d' --host strict > /dev/null
PYTHONDONTWRITEBYTECODE=1 "$LOOM" command "$CAND" --evidence "$EV" --name data-true -- python3 scene_truth.py > /dev/null
python3 -I -c "
import json, sys
for n in ('grammar', 'meaning', 'traps', 'data-true'):
    r = json.load(open(f'{sys.argv[1]}/{n}.json'))
    m = r['measurements']
    tail = m['stdout_tail'].splitlines()[-1] if 'stdout_tail' in m else json.dumps(m.get('seen', r['coverage']))
    print(f\"{n}: {r['status']}  {tail[:160]}\")
" "$EV"

echo "--- controls: the data-true reader must catch each of nine one-line edits with its own code"
python3 -I "$V1/kit/examples/zinc_scene_truth_controls.py" "$CAND" "$(command -v python3)" "$RUN/control-data-true.json"

for w in behaviour page-traps simulation; do
  "$LOOM" record "$CAND" --evidence "$EV" --name "$w" --status not_run --grade L \
    --reason "Static scenes: no ROUTEs, scripts or host page, and nothing was simulated." > /dev/null
done
[ -f "$EV/eyes.json" ] || "$LOOM" record "$CAND" --evidence "$EV" --name eyes --status not_run --grade L \
  --reason "Renders not yet read for this candidate." > /dev/null

"$LOOM" accept  "$CAND" --evidence "$EV" --profile "$V1/kit/profiles/zinc-scenes.json" > /dev/null
"$LOOM" receipt "$CAND" --evidence "$EV" --profile "$V1/kit/profiles/zinc-scenes.json" \
  --subject "Zinc finger Site scenes, model 1 of 14 deposited structures (wwPDB snapshot 2026-01-01)" \
  --out "$RUN/receipt.json" --force
"$LOOM" verify-receipt "$RUN/receipt.json"
echo "done: $RUN"
