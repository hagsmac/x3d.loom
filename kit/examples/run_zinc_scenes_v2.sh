#!/bin/sh
# P1 Site scenes, look v2 (X3D 4.1): the look gains of the remix audit folded back, judged by the same witnesses
# plus a v2 data-true reader that also checks element colours, coordination cages and donor names.
# 1. copy the pinned structures, write the specs, generate the studio cube map (32 px faces: software GL renders it);
# 2. build one v2 scene per structure; 3. grammar, meaning, traps, data-true v2; 4. fifteen negative controls;
# 5. accept and a receipt. The eyes record is written after the renders are read (graded S); rerun the receipt then.
# Usage: kit/examples/run_zinc_scenes_v2.sh RUN_DIR [STRUCTURES_CANDIDATE]. Needs a python3 with MDAnalysis and
# Pillow on PATH and the fork checkout at ~/Projects/x3d/x3d_mcp (or LOOM_FORK). The v1 run is not touched.
set -eu
V1="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="${1:-$V1/runs/zinc-scenes-v2-$(date -u +%Y%m%d)}"
SRC="${2:-$V1/runs/zinc-structures-20261106/candidate}"
CAND="$RUN/candidate"
EV="$RUN/evidence"
LOOM="$V1/kit/loom"
PROFILE="$V1/kit/profiles/zinc-scenes-v2.json"

rm -rf "$EV" "$CAND"; mkdir -p "$EV" "$CAND/scenes"
cp -r "$SRC/structures" "$CAND/"
IDS="$(python3 -I "$V1/kit/examples/zinc_structures.py" "$CAND")"
cp "$V1/kit/examples/zinc_scene_truth.py" "$CAND/scene_truth.py"
cp "$V1/kit/examples/zinc_scene_truth_v2.py" "$CAND/scene_truth_v2.py"
python3 -I "$V1/kit/examples/zinc_studio_env.py" "$CAND/scenes/env" 32
for id in $IDS; do
  python3 -I "$V1/kit/examples/zinc_site_scene_v2.py" "$CAND" "$id" "$CAND/scenes/$id.x3d"
done
"$LOOM" candidate "$CAND"

"$LOOM" grammar "$CAND" --evidence "$EV" --files 'scenes/*.x3d' > /dev/null
"$LOOM" traps "$CAND" --evidence "$EV" --files 'scenes/*.x3d' --host strict > /dev/null
PYTHONDONTWRITEBYTECODE=1 "$LOOM" command "$CAND" --evidence "$EV" --name data-true -- python3 scene_truth_v2.py > /dev/null
python3 -I -c "
import json, sys
for n in ('grammar', 'meaning', 'traps', 'data-true'):
    r = json.load(open(f'{sys.argv[1]}/{n}.json'))
    m = r['measurements']
    tail = m['stdout_tail'].splitlines()[-1] if 'stdout_tail' in m else json.dumps(m.get('seen', r['coverage']))
    print(f\"{n}: {r['status']}  {tail[:160]}\")
" "$EV"

echo "--- controls: the v2 reader must catch nine v1 edits and six v2 edits, each with its own code"
python3 -I "$V1/kit/examples/zinc_scene_truth_v2_controls.py" "$CAND" "$(command -v python3)" "$RUN/control-data-true.json"

for w in behaviour page-traps simulation; do
  "$LOOM" record "$CAND" --evidence "$EV" --name "$w" --status not_run --grade L \
    --reason "Static scenes: no ROUTEs, scripts or host page, and nothing was simulated." > /dev/null
done
[ -f "$EV/eyes.json" ] || "$LOOM" record "$CAND" --evidence "$EV" --name eyes --status not_run --grade L \
  --reason "Renders not yet read for this candidate." > /dev/null

"$LOOM" accept  "$CAND" --evidence "$EV" --profile "$PROFILE" > /dev/null
"$LOOM" receipt "$CAND" --evidence "$EV" --profile "$PROFILE" \
  --subject "Zinc finger Site scenes, look v2, model 1 of 14 deposited structures (wwPDB snapshot 2026-01-01)" \
  --out "$RUN/receipt.json" --force
"$LOOM" verify-receipt "$RUN/receipt.json"
echo "done: $RUN"
