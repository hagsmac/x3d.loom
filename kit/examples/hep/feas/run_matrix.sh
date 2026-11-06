#!/bin/sh
# Load/size matrix (part 1). One fresh Chromium per scene, software GL (SwiftShader). Run alone: other work perturbs CPU timings.
cd "$(dirname "$0")"
node bench.cjs --scenes towers_inst_1000.x3d,towers_merged_1000.x3d,towers_inst_10000.x3d,towers_merged_10000.x3d,towers_merged_50000.x3d --window 3 --timeout 400000 --out results_towers.json > log_bench_towers.txt 2>&1
for c in shells points mesh; do node bench.cjs --cat $c --window 3 --timeout 400000 --out results_$c.json > log_bench_$c.txt 2>&1; done
echo done > bench_all.done
