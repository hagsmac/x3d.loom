#!/bin/sh
# Remaining experiments (part 2), sequential, one fresh Chromium each. Software GL (SwiftShader): relative cost only.
cd "$(dirname "$0")"
node exp.cjs info > log_exp_info.txt 2>&1
node exp.cjs freeze > log_exp_freeze.txt 2>&1
node exp.cjs pick thin thick anchor proxy ribbon > log_exp_pick.txt 2>&1
node exp.cjs picksensor > log_exp_picksensor.txt 2>&1
node bench.cjs --scenes tube_ils1_100.x3d,tube_ils4_100.x3d,tube_tube6_100.x3d,tube_cross_100.x3d,tube_ext_100.x3d,tube_ils1_1000.x3d,tube_ils4_1000.x3d,tube_tube6_1000.x3d,tube_cross_1000.x3d,tube_ext_1000.x3d --window 3 --timeout 300000 --out results_tubes.json > log_bench_tubes.txt 2>&1
node bench.cjs --scenes anim_coordinterp_300.x3d,anim_script_ci_300.x3d,anim_marker_300.x3d,anim_coordinterp_1000.x3d,anim_script_ci_1000.x3d,anim_marker_1000.x3d --window 4 --extra orbit=0 --timeout 300000 --out results_anim.json > log_bench_anim.txt 2>&1
node bench.cjs --dir looks --scenes hero_S1_300_anim.x3d,hero_S2_300_anim.x3d,hero_S1_3000_anim.x3d,hero_S4_300_anim.x3d --window 4 --extra orbit=0 --timeout 600000 --out results_hero_anim.json > log_bench_hero_anim.txt 2>&1
node bench.cjs --scenes shellx_cost_4.x3d,shellx_cost_16.x3d,shellx_cost_64.x3d --window 3 --timeout 300000 --out results_shellcost.json > log_bench_shellcost.txt 2>&1
node bench.cjs --scenes shellx_cost_4.x3d,shellx_cost_16.x3d,shellx_cost_64.x3d --window 3 --extra oit=1 --timeout 300000 --out results_shellcost_oit.json > log_bench_shellcost_oit.txt 2>&1
echo done > rest.done
