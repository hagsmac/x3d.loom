#!/bin/sh
# P1 of the zinc finger study: the metal-site witness on 14 deposited structures, as fetched from the wwPDB snapshot.
# 1. verify (or fetch with --fetch) the pinned archive files and write one spec per structure;
# 2. one metal-site witness per structure (all models of an NMR ensemble), plus an independent cross-check;
# 3. try to accept the FULL set (expected to reject: P1 keeps its reds) and accept the reference set, write a receipt.
# Usage: kit/examples/run_zinc_structures.sh RUN_DIR [--fetch]. The cross-check needs a python3 with MDAnalysis on PATH.
set -eu
V1="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="${1:-$V1/runs/zinc-structures-$(date -u +%Y%m%d)}"
FETCH="${2:-}"
CAND="$RUN/candidate"
EV="$RUN/evidence"
LOOM="$V1/kit/loom"

rm -rf "$EV" "$RUN/control-evidence"; mkdir -p "$EV" "$CAND"
cp "$V1/kit/examples/zinc_cross_check.py" "$CAND/cross_check.py"
IDS="$(python3 -I "$V1/kit/examples/zinc_structures.py" "$CAND" $FETCH)"
"$LOOM" candidate "$CAND"

for id in $IDS; do
  "$LOOM" metalsite "$CAND" --evidence "$EV" --files "structures/pdb$id.ent.gz" --spec "$CAND/specs/$id.json" \
    --name "metal-site-$id" > /dev/null
done
python3 -I -c "
import json, sys
for i in sys.argv[2:]:
    r = json.load(open(f'{sys.argv[1]}/metal-site-{i}.json'))
    print(f\"{i}: {r['status']:4} sites {r['coverage']['sites']}  {r['reason'][:150]}\")
" "$EV" $IDS

# Independent reader (law 25): a second library parses the same archive files and recomputes every zinc-donor
# distance in every model; it must agree with the metal-site witness to 0.001 A.
PYTHONDONTWRITEBYTECODE=1 "$LOOM" command "$CAND" --evidence "$EV" --name cross-check -- python3 cross_check.py ../evidence
python3 -I -c "import json,sys; r=json.load(open(sys.argv[1])); print('cross-check:', r['status'], r['measurements']['stdout_tail'].splitlines()[-1]); sys.exit(0 if r['status']=='pass' else 1)" "$EV/cross-check.json"
python3 -I "$V1/kit/examples/zinc_census.py" "$CAND" "$RUN" > /dev/null

echo "--- control: the cross-check must catch a witness record moved by 0.01 A"
mkdir -p "$RUN/control-evidence"; cp "$EV"/metal-site-*.json "$RUN/control-evidence/"
python3 -I -c "
import json, sys
p = sys.argv[1] + '/metal-site-1rgo.json'; r = json.load(open(p))
d = r['measurements']['structures/pdb1rgo.ent.gz']['sites'][0]['first_frame']['distances'][0]; d['angstrom'] += 0.01
json.dump(r, open(p, 'w'))" "$RUN/control-evidence"
if (cd "$CAND" && PYTHONDONTWRITEBYTECODE=1 python3 cross_check.py ../control-evidence > ../control-cross-check.txt); then
  echo "SURVIVING_CONTROL cross-check"; exit 1; fi
grep DISAGREE "$RUN/control-cross-check.txt"

for w in simulation grammar meaning traps page-traps behaviour eyes; do
  "$LOOM" record "$CAND" --evidence "$EV" --name "$w" --status not_run --grade L \
    --reason "P1 checks deposited structures only: no simulation ran and the Site scenes are judged in their own run."
done

echo "--- the full set: expected to reject on its first red (P1 keeps its reds)"
if "$LOOM" accept "$CAND" --evidence "$EV" --profile "$V1/kit/profiles/zinc-structures-full.json" > "$RUN/control-full-set.json"; then
  echo "SURVIVING_CONTROL full set"; exit 1; fi
cat "$RUN/control-full-set.json"
"$LOOM" accept  "$CAND" --evidence "$EV" --profile "$V1/kit/profiles/zinc-structures.json" > /dev/null
"$LOOM" receipt "$CAND" --evidence "$EV" --profile "$V1/kit/profiles/zinc-structures.json" \
  --subject "Zinc finger structures as deposited (wwPDB snapshot 2026-01-01), P1 reference set" \
  --out "$RUN/receipt.json" --force
"$LOOM" verify-receipt "$RUN/receipt.json"
echo "done: $RUN"
