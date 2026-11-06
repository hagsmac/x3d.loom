#!/bin/sh
# Rehearse the zinc-site instrument path on a SYNTHETIC candidate (no protein, no simulation):
# 1. write the deterministic candidate (two PDB-format files and their spec) into the run folder;
# 2. run the metal-site witness, record what did not run, accept under zinc-site/v0, write a receipt;
# 3. prove the gate bites: an edit after the witness ran rejects (STALE_WITNESS), and a candidate whose
#    zinc has lost a cysteine fails the witness and so cannot be accepted. The trajectory file sorts first, so
#    the intended code is SITE_INTACT_FRACTION (0 of 20 frames) with SITE_COORDINATION as its first failure.
set -eu
V1="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="${1:-$V1/runs/zinc-site-$(date -u +%Y%m%d)}"
CAND="$RUN/candidate"
EV="$RUN/evidence"
WORK="$V1/.work/zinc-site"
LOOM="$V1/kit/loom"
PROFILE="$V1/kit/profiles/zinc-site.json"
FIX="python3 -I $V1/kit/examples/zinc_site_fixtures.py"

rm -rf "$CAND" "$EV" "$RUN/control-evidence" "$WORK"; mkdir -p "$EV" "$WORK"
$FIX "$CAND"

"$LOOM" candidate "$CAND"
"$LOOM" metalsite "$CAND" --evidence "$EV" --files 'structures/*.pdb' --spec "$CAND/metal-site-spec.json"
"$LOOM" record "$CAND" --evidence "$EV" --name real-structure --status not_run --grade L \
  --reason "No experimental zinc-finger structure reached this machine: the structure archives are not reachable from it. The first real run uses an NMR or crystal structure fetched by the operator."
"$LOOM" record "$CAND" --evidence "$EV" --name simulation --status not_run --grade L \
  --reason "No molecular dynamics ran. The engine and analysis library install and pass their own self-tests on CPU here; production runs need a GPU and the operator's yes."
for w in grammar meaning traps page-traps behaviour eyes; do
  "$LOOM" record "$CAND" --evidence "$EV" --name "$w" --status not_run --grade L \
    --reason "No X3D scene exists yet: this run rehearses the structure witness only."
done

"$LOOM" accept  "$CAND" --evidence "$EV" --profile "$PROFILE"
"$LOOM" receipt "$CAND" --evidence "$EV" --profile "$PROFILE" \
  --subject "Synthetic zinc-site candidate (instrument rehearsal, no protein)" \
  --out "$RUN/receipt.json" --outputs "$CAND/structures/ccch-site.pdb" "$CAND/structures/ccch-site-20-frames.pdb" --force
"$LOOM" verify-receipt "$RUN/receipt.json"

echo "--- control: edit a structure after the witness ran -> STALE_WITNESS"
cp -R "$CAND/." "$WORK/"
printf 'REMARK   1 hand edit\n' >> "$WORK/structures/ccch-site.pdb"
if "$LOOM" accept "$WORK" --evidence "$EV" --profile "$PROFILE" > "$RUN/control-stale.json"; then echo "SURVIVING_CONTROL stale"; exit 1; fi
cat "$RUN/control-stale.json"

echo "--- control: zinc has lost a cysteine (3.6 angstrom) -> SITE_INTACT_FRACTION, acceptance rejects"
rm -rf "$WORK"; mkdir -p "$WORK"
$FIX "$WORK" --drifted
"$LOOM" metalsite "$WORK" --evidence "$RUN/control-evidence" --files 'structures/*.pdb' --spec "$WORK/metal-site-spec.json" > /dev/null
python3 -I -c "import json,sys; r=json.load(open(sys.argv[1])); print({'status': r['status'], 'reason': r['reason']}); sys.exit(0 if r['status']=='fail' and r['reason'].startswith('SITE_INTACT_FRACTION: ZN A101: intact in 0 of 20 frames') and 'first failure at frame 0: SITE_COORDINATION' in r['reason'] else 1)" "$RUN/control-evidence/metal-site.json"
if "$LOOM" accept "$WORK" --evidence "$RUN/control-evidence" --profile "$PROFILE" > "$RUN/control-drifted.json"; then echo "SURVIVING_CONTROL drifted"; exit 1; fi
cat "$RUN/control-drifted.json"
rm -rf "$WORK"
echo "done: $RUN"
