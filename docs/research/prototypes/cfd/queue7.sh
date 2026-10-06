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
while pgrep -f "^/bin/bash ./queue6.sh" >/dev/null; do sleep 5; done
echo "[queue7] start $(date)"
# RANS low-Re SST continuation (wall functions diverge, see stage2), restart from stage-1 solution
R=runs/rans_m2_a0_bl_sf3
mkdir -p $R/stage2_wf_failed && mv $R/run.log $R/history.csv $R/walltime.txt $R/stage2_wf_failed/ 2>/dev/null
$PY make_cfg.py $R meshes/rocket_bl_sf3_split.su2 --solver RANS --turb SST --mach 2.0 --aoa 0 --iter 900 --cfl 1 --cflmax 20 --resmin -6 --restart > /dev/null
go $R
$PY postprocess.py $R --aoa 0 > /dev/null 2>&1
# uncontended parallel-mode timing on the u2.0 mesh (148k nodes), Euler no-MG, 25 iterations
for mode in omp1 omp2 mpi2; do
  D=runs_mem/par_$mode; $PY make_cfg.py $D meshes/rocket_u2.0_small.su2 --mach 2 --aoa 4 --iter 25 --mg 0 > /dev/null
  sed -i 's/^SCREEN_WRT_FREQ_INNER= 20/SCREEN_WRT_FREQ_INNER= 1/' $D/case.cfg
  case $mode in
    omp1) (cd $D && $SU2 -t 1 case.cfg > run.log 2>&1);;
    omp2) (cd $D && $SU2 -t 2 case.cfg > run.log 2>&1);;
    mpi2) (cd $D && $B/venv/bin/mpiexec -n 2 $B/su2/SU2-v8.5.0-linux64-mpi/bin/SU2_CFD case.cfg > run.log 2>&1);;
  esac
  echo "[queue7] $mode: $($PY hist.py $D/history.csv 1000 | tail -1)"
done
echo "[queue7] ALL DONE $(date)"
