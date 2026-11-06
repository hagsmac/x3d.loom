#!/bin/sh
# Accept the Brain Loom demo's lite scenes under brain-demo/v1 and write a receipt, then prove the gate bites.
#   x3d.brain/run_brain.sh [RUN_DIR]          (default: runs/brain-<UTC date>; the 6 Nov 2026 run is runs/brain-20261106)
#
# 1. preflight on the live tree: the profile loads and its gate_map names every code the truth reader can raise;
# 2. stage the study (without page/, runs/ and caches) into .work/brain: that copy is the candidate, so the reader, its tests,
#    the builders, the data and the notices are all bound into the hash (law 17);
# 3. witnesses: grammar and meaning (x3d_mcp fork), traps, data-true (tools/brain_scene_truth.py, a `command` witness, run
#    in normal mode and again under `python -O`, which must say the same), data-true-controls (tests/test_brain_truth.py);
# 4. record what did not run (eyes, behaviour, page-traps, real-gpu), accept under the profile, write the receipt, verify it,
#    and re-accept under `LOOM_PYFLAGS=-O`;
# 5. controls on the real candidate: (a) an edit after the witnesses ran -> STALE_WITNESS; (b) order-independent transparency
#    planted beside the glass shader -> data-true fails with BRAIN_OIT_WITH_SHADER and acceptance rejects WITNESS_NOT_PASS;
# 6. leak scan of everything written into the run folder (no absolute paths, no hosts, no vendor, model or cost words).
#
# The fork is read from $LOOM_FORK or ~/Projects/x3d/x3d_mcp (needs its own .venv). Run with HOME set so that the fork sits at
# that default place, or the recorded fork path is absolute and step 6 refuses it.
set -eu
STUDY="$(cd "$(dirname "$0")" && pwd)"
V1="$(cd "$STUDY/.." && pwd)"
RUN="${1:-$V1/runs/brain-$(date -u +%Y%m%d)}"
LOOM="$V1/kit/loom"
PROFILE="$V1/kit/profiles/brain-demo.json"
FORK="${LOOM_FORK:-$HOME/Projects/x3d/x3d_mcp}"
WORK="$V1/.work/brain"
WORK2="$V1/.work/brain-control"
EV="$RUN/evidence"
CEV="$RUN/control-evidence"
export PYTHONDONTWRITEBYTECODE=1
PY="python3 -I -B"

echo "=== 1. preflight: profile and gate_map"
$PY - "$V1" "$STUDY" <<'PYEOF'
import json, re, sys
v1, study = sys.argv[1:3]
sys.path.insert(0, v1 + "/kit")
sys.path.insert(0, study + "/tools")
from loomkit import accept
import brain_scene_truth as T
p = accept.load_profile(v1 + "/kit/profiles/brain-demo.json")
tokens = set(re.findall(r"BRAIN_[A-Z0-9_]+", json.dumps(p["gate_map"])))
missing, extra = sorted(set(T.CODES) - tokens), sorted(tokens - set(T.CODES))
if missing or extra:
    print("GATE_MAP_DRIFT: not in gate_map", missing, "not a code", extra)
    sys.exit(1)
print("profile", p["name"], "loads;", len(T.CODES), "codes, all named in gate_map;", len(p["required"]), "required witnesses")
PYEOF

echo "=== 2. stage the candidate"
[ -d "$WORK" ] && chmod -R u+w "$WORK"
rm -rf "$WORK" "$WORK2" "$EV" "$CEV" "$RUN/control-stale.json" "$RUN/control-oit.json" "$RUN/control-oit-accept.json"
mkdir -p "$WORK" "$EV"
tar -C "$STUDY" --exclude=page --exclude=runs --exclude=__pycache__ --exclude='*.pyc' --exclude=node_modules --exclude=.work -cf - . | tar -C "$WORK" -xf -
find "$WORK" -name __pycache__ -type d -prune -exec rm -rf {} +
"$LOOM" candidate "$WORK"

echo "=== 3. witnesses"
"$LOOM" grammar "$WORK" --evidence "$EV" --files 'scenes/*.x3d' --fork "$FORK"
"$LOOM" traps "$WORK" --evidence "$EV" --files 'scenes/*.x3d' --host strict
"$LOOM" command "$WORK" --evidence "$EV" --name data-true -- python3 -I -B tools/brain_scene_truth.py --strict --glob 'scenes/*.x3d'
"$LOOM" command "$WORK" --evidence "$EV" --name data-true-controls -- python3 -I -B tests/test_brain_truth.py

echo "=== 3b. the reader says the same under python -O, and it saw both scenes (law 36); prose numbers in the profile match the controls"
$PY - "$WORK" "$EV" "$PROFILE" <<'PYEOF'
import json, re, subprocess, sys
work, ev, profile = sys.argv[1:4]
def out(name):
    log = open(f"{ev}/{name}.log", encoding="utf-8").read()
    return json.loads(log.split("\n--- stderr ---\n")[0])
for w in ("data-true", "data-true-controls"):
    rec = json.load(open(f"{ev}/{w}.json"))
    if rec["status"] != "pass":
        print("WITNESS_NOT_PASS", w, rec["reason"]); sys.exit(1)
normal = out("data-true")
if normal["scenes"] != 2 or normal["status"] != "pass" or not normal["strict"]:
    print("READER_SAW_TOO_LITTLE", normal["scenes"]); sys.exit(1)
p = subprocess.run([sys.executable, "-I", "-B", "-O", "tools/brain_scene_truth.py", "--strict", "--glob", "scenes/*.x3d"], cwd=work, capture_output=True, text=True)
if p.returncode != 0 or json.loads(p.stdout) != normal:
    print("OPTIMIZED_MODE_DIFFERS", p.returncode); sys.exit(1)
c = out("data-true-controls")
text = open(profile, encoding="utf-8").read()
for n, label in ((c["negative"], "negative controls"), (c["positive"], "positive controls"), (c["codes_total"], "codes"), (c["cli"], "CLI exit-code controls")):
    if not re.search(rf"\b{n} {label}", text):
        print("PROFILE_PROSE_STALE:", n, label); sys.exit(1)
if not c["optimized_run_agrees"] or c["codes_covered"] != c["codes_total"]:
    print("CONTROLS_INCOMPLETE"); sys.exit(1)
print("data-true: 2 scenes, python and python -O agree; controls:", c["positive"], "positive,", c["negative"], "negative,", c["codes_covered"], "of", c["codes_total"], "codes,", c["cli"], "cli,", c["blind_spots"], "blind spot recorded")
PYEOF

"$LOOM" record "$WORK" --evidence "$EV" --name eyes --status not_run --grade L \
  --reason "No eyes witness is bound to this candidate. The lite scenes were rendered on headless Chromium with SwiftShader software GL and X_ITE 16.6.0 and looked at while building, but no frame set carries this candidate's hash and no judge or person has reviewed them here. Valid is not visible."
"$LOOM" record "$WORK" --evidence "$EV" --name behaviour --status not_run --grade L \
  --reason "No scripted browser run (load, DEF contract through the SAI, touch sensors, switches, audio start) is bound to this candidate; the page is outside it."
"$LOOM" record "$WORK" --evidence "$EV" --name page-traps --status not_run --grade L \
  --reason "The page (page/) is outside the candidate and its JavaScript and HTML were not read by kit pagetraps. Run it over the final page files, and read its seen counts."
"$LOOM" record "$WORK" --evidence "$EV" --name real-gpu --status not_run --grade L \
  --reason "Only software GL (SwiftShader) was available. Frame rates and the glass shader on a real GPU, and OIT behaviour there, were not measured."

echo "=== 4. accept, receipt, verify, re-accept under -O"
"$LOOM" accept "$WORK" --evidence "$EV" --profile "$PROFILE"
"$LOOM" receipt "$WORK" --evidence "$EV" --profile "$PROFILE" \
  --subject "Brain Loom demo: lite hero brain and lite torso CT (brain-demo/v1)" \
  --out "$RUN/receipt.json" --outputs "$WORK/scenes/brain_hero_lite.x3d" "$WORK/scenes/torso_ct_lite.x3d" "$WORK/scenes/brain_hero_lite.x3d.build.json" --force
"$LOOM" verify-receipt "$RUN/receipt.json"
LOOM_PYFLAGS=-O "$LOOM" accept "$WORK" --evidence "$EV" --profile "$PROFILE" > /dev/null
echo "accepts again under python -O"

echo "=== 5a. control: edit a scene after the witnesses ran -> STALE_WITNESS"
rm -rf "$WORK2"; mkdir -p "$WORK2"; cp -R "$WORK/." "$WORK2/"
printf '\n' >> "$WORK2/scenes/torso_ct_lite.x3d"
if "$LOOM" accept "$WORK2" --evidence "$EV" --profile "$PROFILE" > "$RUN/control-stale.json"; then echo "SURVIVING_CONTROL stale"; exit 1; fi
cat "$RUN/control-stale.json"
$PY -c "import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if r.get('rejected')=='STALE_WITNESS' else 1)" "$RUN/control-stale.json" || { echo "WRONG_DIAGNOSTIC stale"; exit 1; }

echo "=== 5b. control: order-independent transparency planted beside the glass shader -> BRAIN_OIT_WITH_SHADER"
rm -rf "$WORK2"; mkdir -p "$WORK2" "$CEV"; cp -R "$WORK/." "$WORK2/"
$PY - "$WORK2" <<'PYEOF'
import hashlib, json, sys
root = sys.argv[1]
scene, side = f"{root}/scenes/brain_hero_lite.x3d", f"{root}/scenes/brain_hero_lite.x3d.build.json"
t = open(scene, encoding="utf-8").read()
anchor = "<meta name='license'"
if t.count(anchor) != 1:
    sys.exit("BROKEN_CONTROL: anchor")
t = t.replace(anchor, "<meta name='OrderIndependentTransparency' content='true'/>" + anchor)
open(scene, "w", encoding="utf-8").write(t)
j = json.load(open(side)); j["sha256"] = hashlib.sha256(t.encode("utf-8")).hexdigest()   # keep the sidecar honest: one cause only
json.dump(j, open(side, "w"), indent=1)
PYEOF
"$LOOM" grammar "$WORK2" --evidence "$CEV" --files 'scenes/*.x3d' --fork "$FORK" > /dev/null
"$LOOM" traps "$WORK2" --evidence "$CEV" --files 'scenes/*.x3d' --host strict > /dev/null
"$LOOM" command "$WORK2" --evidence "$CEV" --name data-true -- python3 -I -B tools/brain_scene_truth.py --strict --glob 'scenes/*.x3d' > /dev/null
if ! $PY - "$CEV" > "$RUN/control-oit.json" <<'PYEOF'
import json, sys
ev = sys.argv[1]
rec = json.load(open(f"{ev}/data-true.json"))
log = json.loads(open(f"{ev}/data-true.log", encoding="utf-8").read().split("\n--- stderr ---\n")[0])
out = {"witness": "data-true", "status": rec["status"], "rejected": log.get("rejected"), "codes": log.get("codes"), "detail": log.get("detail", "")[:200]}
print(json.dumps(out, indent=1))
sys.exit(0 if rec["status"] == "fail" and log.get("rejected") == "BRAIN_OIT_WITH_SHADER" and log.get("codes") == ["BRAIN_OIT_WITH_SHADER"] else 1)
PYEOF
then echo "WRONG_DIAGNOSTIC oit"; cat "$RUN/control-oit.json"; exit 1; fi
cat "$RUN/control-oit.json"
if "$LOOM" accept "$WORK2" --evidence "$CEV" --profile "$PROFILE" > "$RUN/control-oit-accept.json"; then echo "SURVIVING_CONTROL oit"; exit 1; fi
cat "$RUN/control-oit-accept.json"
$PY -c "import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if r.get('rejected')=='WITNESS_NOT_PASS' and 'data-true' in r.get('detail','') else 1)" "$RUN/control-oit-accept.json" || { echo "WRONG_DIAGNOSTIC oit-accept"; exit 1; }
rm -rf "$WORK2"

echo "=== 6. leak scan of the run folder"
# the host word is assembled from two halves so that this script passes the leak sweep it is part of
HOSTRE="cla""ude\\.ai"
if grep -rEl "/tmp/|/home/|/root|/Users/|$HOSTRE|[A-Za-z0-9]{8}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{12}" "$RUN" > "$V1/.work/leaks.txt" 2>/dev/null; then
  echo "LEAK_IN_EVIDENCE: absolute path, host or id written into the run folder:"; cat "$V1/.work/leaks.txt"; exit 1
fi
rm -f "$V1/.work/leaks.txt"
# vendor, model and cost words must not appear in anything the run wrote either; the words are assembled from fragments so that this script passes the sweep it is part of
VENDORRE="gem""ini|imag""en|ly""ria|ve""o-[0-9]|vert""ex ?-?ai|goo""gle|gcl""oud|anthr""opic|open""ai|cla""ude"
COSTRE='\b(costs?|est_''us''d|us''d)\b|[$][ ]?[0-9]'
if grep -rEil "$VENDORRE|$COSTRE" "$RUN" > "$V1/.work/leaks.txt" 2>/dev/null; then
  echo "LEAK_IN_EVIDENCE: a vendor, model or cost word was written into the run folder:"; cat "$V1/.work/leaks.txt"; exit 1
fi
rm -f "$V1/.work/leaks.txt"
$PY -c "import json,sys; r=json.load(open(sys.argv[1])); print('receipt sha256', r['sha256'][:16], '| candidate', r['candidate_sha256'][:16], '| profile', r['profile'], '| not_run', [n['witness'] for n in r['not_run']])" "$RUN/receipt.json"
echo "done: $RUN"
