#!/usr/bin/env python3
"""Merge results_*.json from bench.cjs into compact markdown tables (stdlib only).
   python3 summarize.py results_tracks.json [...]   -> markdown on stdout
Relative cost = raf main-thread ms per frame divided by the smallest scene's value in the same table (software GL: never a frame rate)."""
import json, sys

def num(v, nd=0):
    return '-' if v is None else (('%.' + str(nd) + 'f') % v)

def table(files, cols=None):
    rows = []
    for f in files:
        d = json.load(open(f))
        rows += d['rows']
    base = None
    out = ['| scene | file MB (gz) | XML elems | parse+build s | replaceWorld s | distinct nodes | JS heap MB | draws/tick | CPU ms/tick (rAF cb) | rel. CPU | console err | note |', '|---|---|---|---|---|---|---|---|---|---|---|---|']
    ticks = lambda r: (r.get('window_frames') or 0)
    vals = []
    for r in rows:
        g = r.get('gl') or {}
        vals.append(g.get('raf_main_thread_ms_mean'))
    good = [v for v in vals if v]
    base = min(good) if good else None
    for r, v in zip(rows, vals):
        g = r.get('gl') or {}
        fr = max(1, ticks(r))
        dpt = (g.get('draw') or 0) / fr if g else None
        note = ''
        if r.get('timeout_or_fail'):
            note = 'FAILED/timeout: ' + r['timeout_or_fail'][:60]
        elif r.get('errors'):
            note = r['errors'][0][:60]
        out.append('| %s | %s (%s) | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            r['name'], num(r.get('file_mb'), 2), num(r.get('gz_mb'), 2), r.get('xml_elements', '-'),
            num((r.get('t_parse_build_ms') or 0) / 1000 if r.get('t_parse_build_ms') is not None else None, 2),
            num((r.get('t_replace_ms') or 0) / 1000 if r.get('t_replace_ms') is not None else None, 2),
            r.get('nodes_distinct', '-'), num(r.get('js_heap_mb'), 0), num(dpt, 0) if dpt is not None else '-',
            num(v, 2) if v else '-', ('%.1fx' % (v / base)) if (v and base) else '-', r.get('console_errors', '-'), note))
    return '\n'.join(out)

if __name__ == '__main__':
    print(table(sys.argv[1:]))
