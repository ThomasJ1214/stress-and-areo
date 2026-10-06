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
while pgrep -x SU2_CFD >/dev/null; do sleep 5; done
echo "[queue6] start $(date)"
$PY postprocess.py runs/m01_a4_sf3_roe --aoa 4 --mach 0.1 > /dev/null 2>&1
# low Mach M=0.1 AoA 4: Roe + low-Mach correction, incompressible solver (forces converge in ~200 its)
$PY make_cfg.py runs/m01_a4_sf3_roe_lmcorr meshes/rocket_sf3.su2 --mach 0.1 --aoa 4 --iter 250 --mg 3 --cflmax 100 --lowmach --resmin -7 > /dev/null
go runs/m01_a4_sf3_roe_lmcorr
$PY postprocess.py runs/m01_a4_sf3_roe_lmcorr --aoa 4 --mach 0.1 > /dev/null 2>&1
$PY make_cfg.py runs/m01_a4_sf3_inc meshes/rocket_sf3.su2 --solver INC_EULER --mach 0.1 --aoa 4 --iter 250 --mg 3 --cflmax 100 --resmin -7 > /dev/null
go runs/m01_a4_sf3_inc
$PY postprocess.py runs/m01_a4_sf3_inc --aoa 4 --mach 0.1 > /dev/null 2>&1
# systematic (uniform) refinement study, small supersonic domain: sf = 2.8, 2.0, 1.4
for sfv in 2.8 2.0 1.4; do
  [ -s meshes/rocket_u${sfv}_small.su2 ] || $PY make_mesh.py meshes/rocket_u${sfv}_small.su2 $sfv --small-domain --uniform > meshes/rocket_u${sfv}_small.log 2>&1
  echo "[queue6] mesh u$sfv: $(grep -E '^\[mesh\] elements3D' meshes/rocket_u${sfv}_small.log)"
  for aoa in 0 4; do
    $PY make_cfg.py runs/m2_a${aoa}_u${sfv} meshes/rocket_u${sfv}_small.su2 --mach 2.0 --aoa $aoa --iter 150 --mg 3 --cflmax 100 --resmin -5.5 > /dev/null
    go runs/m2_a${aoa}_u${sfv}
    $PY postprocess.py runs/m2_a${aoa}_u${sfv} --aoa $aoa > /dev/null 2>&1
  done
done
# RANS SST on the gmsh prism mesh: stage 1 low-Re SST start-up, stage 2 restart with wall functions
R=runs/rans_m2_a0_bl_sf3
rm -rf $R
$PY make_cfg.py $R meshes/rocket_bl_sf3_split.su2 --solver RANS --turb SST --mach 2.0 --aoa 0 --iter 300 --cfl 0.5 --cflmax 20 --resmin -12 > /dev/null
go $R
mkdir -p $R/stage1 && cp $R/history.csv $R/run.log $R/walltime.txt $R/peak_rss.txt $R/forces_breakdown.dat $R/stage1/ 2>/dev/null
$PY make_cfg.py $R meshes/rocket_bl_sf3_split.su2 --solver RANS --turb SST --wallfunc --mach 2.0 --aoa 0 --iter 1200 --cfl 2 --cflmax 30 --resmin -6 --restart > /dev/null
go $R
$PY postprocess.py $R --aoa 0 > /dev/null 2>&1
# limiter sensitivity on the sf2 mesh (AoA 0)
$PY make_cfg.py runs/m2_a0_sf2_K0.3 meshes/rocket_sf2.su2 --mach 2.0 --aoa 0 --iter 150 --mg 3 --cflmax 100 --venkat 0.3 --resmin -5.5 > /dev/null
go runs/m2_a0_sf2_K0.3
$PY postprocess.py runs/m2_a0_sf2_K0.3 --aoa 0 > /dev/null 2>&1
echo "[queue6] ALL DONE $(date)"
