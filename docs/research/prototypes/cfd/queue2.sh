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

for sfv in 2 3; do
  if [ ! -f meshes/rocket_sf$sfv.su2 ]; then $PY make_mesh.py meshes/rocket_sf$sfv.su2 $sfv > meshes/rocket_sf$sfv.log 2>&1; fi
  echo "[queue] mesh sf$sfv: $(grep -E '^\[mesh\] elements3D' meshes/rocket_sf$sfv.log)"
  for aoa in 0 4; do
    $PY make_cfg.py runs/m2_a${aoa}_sf${sfv} meshes/rocket_sf$sfv.su2 --mach 2.0 --aoa $aoa --iter 400 --mg 3 --cflmax 100 > /dev/null
    go runs/m2_a${aoa}_sf${sfv}
    $PY postprocess.py runs/m2_a${aoa}_sf${sfv} --aoa $aoa > /dev/null 2>&1
  done
done
echo "[queue] ALL DONE $(date)"
