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
while pgrep -f "queue2.sh" >/dev/null; do sleep 10; done
echo "[queue3] start $(date)"
# 1) RANS SST + wall functions on the gmsh prism-layer mesh, M2 AoA 0
$PY make_cfg.py runs/rans_m2_a0_bl_sf3 meshes/rocket_bl_sf3_split.su2 --solver RANS --turb SST --wallfunc --mach 2.0 --aoa 0 --iter 1500 --cfl 2 --cflmax 50 --resmin -6 > /dev/null
go runs/rans_m2_a0_bl_sf3
# 2) low Mach (M=0.1, AoA 4) on the large-domain sf3 tet mesh: plain Roe, Roe + low-Mach correction, incompressible
$PY make_cfg.py runs/m01_a4_sf3_roe meshes/rocket_sf3.su2 --mach 0.1 --aoa 4 --iter 800 --mg 3 --cflmax 100 --resmin -7 > /dev/null
go runs/m01_a4_sf3_roe
$PY make_cfg.py runs/m01_a4_sf3_roe_lmcorr meshes/rocket_sf3.su2 --mach 0.1 --aoa 4 --iter 800 --mg 3 --cflmax 100 --lowmach --resmin -7 > /dev/null
go runs/m01_a4_sf3_roe_lmcorr
$PY make_cfg.py runs/m01_a4_sf3_inc meshes/rocket_sf3.su2 --solver INC_EULER --mach 0.1 --aoa 4 --iter 800 --mg 3 --cflmax 100 --resmin -7 > /dev/null
go runs/m01_a4_sf3_inc
echo "[queue3] ALL DONE $(date)"
