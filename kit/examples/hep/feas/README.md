# Feasibility harness (look v1 study)

The scripts behind [docs/COLLIDER-XITE-FEASIBILITY.md](../../../../docs/COLLIDER-XITE-FEASIBILITY.md): synthetic scene generators (`gen_*.py`, `evtcommon.py`), the WebGL call spy (`glspy.js`), the load bench (`bench.cjs`, `site/bench.html`), stills (`shots.cjs`, `site/shot.html`), callback, picking and info experiments (`exp.cjs`), pixel statistics (`imgtools.py`) and the result tables (`summarize.py`).

X_ITE is not committed. Fetch it with `../render/fetch_xite.sh` and copy `../render/site/x_ite` to `site/x_ite`, or run `npm pack x_ite@16.5.1` and unpack its `dist/` there. Generated scenes (`site/scenes`, `site/looks`), stills (`shots/`), results and logs are ignored by git. Everything here runs on software GL: load times are CPU times, never frame rates.
