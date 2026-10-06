#!/bin/bash
# sequential run queue (2 threads at a time)
set -u
B=/tmp/claude-0/-home-user-stress-and-areo/045926a7-bc8f-54ef-a52e-f5484ae3b45a/scratchpad/research/cfd
SU2=$B/su2/SU2-v8.5.0-linux64-omp/bin/SU2_CFD
PY=$B/venv/bin/python
cd $B
run() { # dir
  ( cd $1 && /usr/bin/env bash -c "start=\$(date +%s.%N); $SU2 -t 2 case.cfg > run.log 2>&1; rc=\$?; end=\$(date +%s.%N); echo \"wall_s=\$(echo \"\$end - \$start\" | bc) rc=\$rc\" > walltime.txt" )
  # peak RSS is captured by a sampler below
}
sample_rss() { # dir
  local peak=0; while pgrep -f "SU2_CFD -t 2 case.cfg" >/dev/null; do
    for p in $(pgrep -f "SU2_CFD -t 2 case.cfg"); do r=$(awk '/VmHWM/{print $2}' /proc/$p/status 2>/dev/null); [ -n "$r" ] && [ "$r" -gt "$peak" ] && peak=$r; done; sleep 2; done; echo "peak_rss_kB=$peak" > $1/peak_rss.txt; }
go() { run $1 & sleep 3; sample_rss $1; wait; echo "[queue] finished $1 $(cat $1/walltime.txt) $(date)"; }
while pgrep -f "queue[23].sh" >/dev/null; do sleep 10; done
echo "[queue4] start $(date)"
# limiter sensitivity on the sf2 mesh (AoA 0): Venkatakrishnan-Wang K=0.3 (less limiting)
$PY make_cfg.py runs/m2_a0_sf2_K0.3 meshes/rocket_sf2.su2 --mach 2.0 --aoa 0 --iter 400 --mg 3 --cflmax 100 --venkat 0.3 > /dev/null
go runs/m2_a0_sf2_K0.3
$PY postprocess.py runs/m2_a0_sf2_K0.3 --aoa 0 > /dev/null 2>&1
# systematic (uniform) refinement study, small supersonic domain: sf = 2.8, 2.0, 1.4 (h ratio sqrt(2))
for sfv in 2.8 2.0 1.4; do
  [ -s meshes/rocket_u${sfv}_small.su2 ] || $PY make_mesh.py meshes/rocket_u${sfv}_small.su2 $sfv --small-domain --uniform > meshes/rocket_u${sfv}_small.log 2>&1
  echo "[queue4] mesh u$sfv: $(grep -E '^\[mesh\] elements3D' meshes/rocket_u${sfv}_small.log)"
  for aoa in 0 4; do
    $PY make_cfg.py runs/m2_a${aoa}_u${sfv} meshes/rocket_u${sfv}_small.su2 --mach 2.0 --aoa $aoa --iter 300 --mg 3 --cflmax 100 --resmin -7 > /dev/null
    go runs/m2_a${aoa}_u${sfv}
    $PY postprocess.py runs/m2_a${aoa}_u${sfv} --aoa $aoa > /dev/null 2>&1
  done
done
echo "[queue4] ALL DONE $(date)"
