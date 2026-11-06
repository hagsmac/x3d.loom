#!/bin/sh
# Rehearse the hep-demo path on the committed fixtures (one hand-computed Z -> mu mu decay and four Pythia 8 events):
# 1. build the candidate: the scene builder writes one X3D scene per fixture (generator, not file) beside an event file
#    that names it, once in look v1 (events/, one Shape per track) and once in look v2 (events-v2/, ribbons merged into
#    strips, muon extensions, tower spikes), and the spec is copied in so it is part of the candidate hash;
# 2. run the hep-event witness and the traps witness, record what did not run, accept under hep-demo/v2, write a receipt;
# 3. prove the gate bites: an edit after the witness ran rejects (STALE_WITNESS), and a hero scene with one track
#    deleted fails the witness with EVT_SCENE_BIJECTION so acceptance rejects it (WITNESS_NOT_PASS), in v1 and in v2.
set -eu
V1="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="${1:-$V1/runs/hep-demo-v2-$(date -u +%Y%m%d)}"
CAND="$RUN/candidate"
EV="$RUN/evidence"
WORK="$V1/.work/hep-demo"
LOOM="$V1/kit/loom"
PROFILE="$V1/kit/profiles/hep-demo.json"
HEP="$V1/kit/examples/hep"

rm -rf "$CAND" "$EV" "$RUN/control-evidence" "$RUN/control-evidence-v2" "$WORK"; mkdir -p "$CAND/events" "$CAND/events-v2" "$EV" "$WORK"
for f in "$HEP"/fixtures/*.event.json; do
  python3 -I "$HEP/build_event_scene.py" "$f" "$CAND/events"
  python3 -I "$HEP/build_event_scene.py" "$f" "$CAND/events-v2" --look v2
done
cp "$HEP/hep-demo-spec.json" "$CAND/hep-demo-spec.json"

"$LOOM" candidate "$CAND"
"$LOOM" hepevent "$CAND" --evidence "$EV" --events 'events/*.event.json,events-v2/*.event.json' --spec "$CAND/hep-demo-spec.json"
"$LOOM" traps "$CAND" --evidence "$EV" --files 'events/*.x3d,events-v2/*.x3d' --host strict
"$LOOM" record "$CAND" --evidence "$EV" --name grammar --status not_run --grade L \
  --reason "The X3D fork is not on this machine. Written against X3D 4.0 (profile Immersive, Shaders level 3 declared); not validated."
"$LOOM" record "$CAND" --evidence "$EV" --name meaning --status not_run --grade L \
  --reason "The X3D fork is not on this machine; DEF before USE and ROUTE order are read by the hep-event and traps witnesses only."
"$LOOM" record "$CAND" --evidence "$EV" --name behaviour --status not_run --grade L \
  --reason "Not run as a Loom witness in this rehearsal. X_ITE 16.5.1 stills of these exact look v2 scenes (0 shader or console errors, software GL) are recorded outside this receipt in the run's frames/ folder (LOOK-V2.md, frames.jsonl)."
"$LOOM" record "$CAND" --evidence "$EV" --name look-match --status not_run --grade S \
  --reason "Not run as a witness: the frames/ pixel statistics against the private reference still (frames/stats.json) are an instrument reading, not an acceptance gate."
"$LOOM" record "$CAND" --evidence "$EV" --name eyes --status not_run --grade L --reason "Not run as a witness: the frames/ stills were looked at by the builder of the scene, which is not an independent eye."
"$LOOM" record "$CAND" --evidence "$EV" --name real-gpu --status not_run --grade L --reason "No GPU timing or frame-rate measurement."

"$LOOM" accept  "$CAND" --evidence "$EV" --profile "$PROFILE"
"$LOOM" receipt "$CAND" --evidence "$EV" --profile "$PROFILE" \
  --subject "Collider-event demo scenes (one exact decay, four Pythia 8 events, look v1 and look v2; instrument rehearsal)" \
  --out "$RUN/receipt.json" --outputs "$CAND/events/pythia-qcd-demo.x3d" "$CAND/events/exact-zmumu.x3d" "$CAND/events-v2/pythia-qcd-demo.x3d" "$CAND/events-v2/pythia-zmumu.x3d" "$CAND/events-v2/pythia-dijet-hero.x3d" --force
"$LOOM" verify-receipt "$RUN/receipt.json"

echo "--- control: edit a scene after the witness ran -> STALE_WITNESS"
cp -R "$CAND/." "$WORK/"
printf '<!-- hand edit -->\n' >> "$WORK/events/pythia-qcd-demo.x3d"
if "$LOOM" accept "$WORK" --evidence "$EV" --profile "$PROFILE" > "$RUN/control-stale.json"; then echo "SURVIVING_CONTROL stale"; exit 1; fi
cat "$RUN/control-stale.json"

echo "--- control: one track deleted from the hero scene -> EVT_SCENE_BIJECTION, acceptance rejects"
rm -rf "$WORK"; mkdir -p "$WORK"; cp -R "$CAND/." "$WORK/"
python3 -I - "$WORK/events/pythia-qcd-demo.x3d" <<'PY'
import re, sys
p = sys.argv[1]; t = open(p).read()
t2, n = re.subn(r"<Shape DEF='trk_7'>.*?</Shape>\n", "", t, count=1, flags=re.S)
if n != 1: raise SystemExit("control could not find trk_7")
open(p, "w").write(t2)
PY
"$LOOM" hepevent "$WORK" --evidence "$RUN/control-evidence" --events 'events/*.event.json' --spec "$WORK/hep-demo-spec.json" > /dev/null
python3 -I -c "import json,sys; r=json.load(open(sys.argv[1])); print({'status': r['status'], 'reason': r['reason']}); sys.exit(0 if r['status']=='fail' and r['reason'].startswith('EVT_SCENE_BIJECTION: event tracks not drawn: trk_7') else 1)" "$RUN/control-evidence/hep-event.json"
"$LOOM" traps "$WORK" --evidence "$RUN/control-evidence" --files 'events/*.x3d' --host strict > /dev/null
if "$LOOM" accept "$WORK" --evidence "$RUN/control-evidence" --profile "$PROFILE" > "$RUN/control-deleted.json"; then echo "SURVIVING_CONTROL deleted"; exit 1; fi
cat "$RUN/control-deleted.json"

echo "--- control (look v2): one track's strip deleted from the merged hero set -> EVT_SCENE_BIJECTION, acceptance rejects"
rm -rf "$WORK"; mkdir -p "$WORK"; cp -R "$CAND/." "$WORK/"
python3 -I - "$WORK/events-v2/pythia-qcd-demo.x3d" <<'PY'
import sys, xml.etree.ElementTree as ET
p = sys.argv[1]; root = ET.parse(p).getroot()
sh = next(e for e in root.iter() if e.get("DEF") == "trkset_0")
g = next(c for c in sh if c.tag == "TriangleStripSet")
co = next(c for c in g if c.tag == "Coordinate")
counts = [int(v) for v in g.get("stripCount").split()]
ident = next(c for c in g if c.get("name") == "a_ident").get("value").split()
start, j = 0, None
for n, c in enumerate(counts):
    if int(float(ident[4 * start])) == 7:
        j = n
        break
    start += c
if j is None: raise SystemExit("control could not find the strip of track 7")
cut = range(start, start + counts[j])
pts = co.get("point").split()
co.set("point", " ".join(v for i, v in enumerate(pts) if i // 3 not in cut))
for f in (c for c in g if c.tag == "FloatVertexAttribute"):
    nc = int(f.get("numComponents")); vals = f.get("value").split()
    f.set("value", " ".join(v for i, v in enumerate(vals) if i // nc not in cut))
g.set("stripCount", " ".join(str(c) for n, c in enumerate(counts) if n != j))
ET.ElementTree(root).write(p, encoding="unicode", xml_declaration=True)
PY
"$LOOM" hepevent "$WORK" --evidence "$RUN/control-evidence-v2" --events 'events/*.event.json,events-v2/*.event.json' --spec "$WORK/hep-demo-spec.json" > /dev/null
python3 -I -c "import json,sys; r=json.load(open(sys.argv[1])); print({'status': r['status'], 'reason': r['reason']}); sys.exit(0 if r['status']=='fail' and r['reason'].startswith('EVT_SCENE_BIJECTION: event tracks not drawn: trk_7') else 1)" "$RUN/control-evidence-v2/hep-event.json"
"$LOOM" traps "$WORK" --evidence "$RUN/control-evidence-v2" --files 'events/*.x3d,events-v2/*.x3d' --host strict > /dev/null
if "$LOOM" accept "$WORK" --evidence "$RUN/control-evidence-v2" --profile "$PROFILE" > "$RUN/control-deleted-v2.json"; then echo "SURVIVING_CONTROL deleted v2"; exit 1; fi
cat "$RUN/control-deleted-v2.json"
rm -rf "$WORK"
echo "done: $RUN"
