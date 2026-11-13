"""Mutation controls on my own records: each edit must be refused with its own code (kit physics witness).
usage: python3 -I mutate.py LOOM_KIT_DIR REPO_ROOT   (LOOM_KIT_DIR is x3d.loom/kit)"""
import sys, json, copy
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from loomkit import physics
from loomkit.core import GateError
ROOT = Path(sys.argv[2]); recs = sorted((ROOT/'docs/demos/ten-minute-physics/v5/witness/records').glob('*.physics.json'))
base = {p.name[:2]: json.loads(p.read_text()) for p in recs}   # '15', '18', '22'
def run(r, **kw):
    kw.setdefault('required_hosts', ['numpy-fresh-process']); return physics.check_run(r, ROOT, **kw)
out = []
def expect(name, code, mut, rec):
    r = copy.deepcopy(base[rec]); mut(r)
    try: run(r)
    except GateError as e:
        out.append(dict(control=name, expected=code, got=e.code, ok=e.code == code)); return
    out.append(dict(control=name, expected=code, got=None, ok=False))
def tamper(r): r['recorded']['hashes'][10] ^= 1
def drop_replay(r): r['replays'] = [x for x in r['replays'] if x['host'] != 'numpy-fresh-process']
def widen(r): r['references'][0]['limit'] *= 1e3
def false_green(r): r['references'][0]['observed'] = r['references'][0]['limit']*10; r['references'][0]['declared_limit'] = r['references'][0]['limit']*100; r['references'][0]['status'] = 'pass'
def ref_fail(r): r['references'][0]['observed'] = r['references'][0]['limit']*10; r['references'][0]['status'] = 'fail'
def drop_refs(r): r['references'] = []
def surviving(r): r['controls'][0]['observed_failed'] = False
def drift(r): r['replays'][0]['mismatches'] = 3; r['replays'][0]['first_mismatch'] = 7
def stale(r): r['model']['sha256'] = '0'*64
def steps(r): r['replays'][0]['steps'] = 5
def engine(r): r['replays'][0]['engine_version'] = 'numpy-0.0'
expect('edited step hash', 'PHYS_TRACE_TAMPERED', tamper, '18')
expect('replay host removed', 'PHYS_REPLAY_MISSING', drop_replay, '22')
expect('limit widened after the fact', 'PHYS_LIMIT_WIDENED', widen, '22')
expect('fail marked pass', 'PHYS_FALSE_GREEN', false_green, '18')
expect('reference misses its limit', 'PHYS_REFERENCE_FAIL', ref_fail, '22')
expect('no reference', 'PHYS_NO_REFERENCE', drop_refs, '15')
expect('control that survives', 'PHYS_CONTROL_SURVIVED', surviving, '22')
expect('replay hash drift', 'PHYS_HASH_DRIFT', drift, '18')
expect('scene changed under the record', 'PHYS_MODEL_STALE', stale, '15')
expect('replay of the wrong length', 'PHYS_REPLAY_STEPS', steps, '22')
expect('engine version drift', 'PHYS_ENGINE_DRIFT', engine, '15')
print(json.dumps(out, indent=1)); print('caught', sum(o['ok'] for o in out), 'of', len(out))
Path(__file__).with_name('mutation-controls.json').write_text(json.dumps(dict(controls=out, caught=sum(o['ok'] for o in out), total=len(out)), indent=1))
