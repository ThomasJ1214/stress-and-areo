#!/bin/bash
# solver benchmark on the 136k-DOF C3D10 static deck (case d1, LC=1.5)
export WINEPREFIX=$PWD/../wineprefix WINEDEBUG=-all
FEA=$PWD/..
run() { name=$1; shift; s=$(date +%s.%N); "$@" > $name.out 2>&1; e=$(date +%s.%N); echo "$name $(echo "$e - $s" | bc) s"; }
cp base.inp sp1.inp; OMP_NUM_THREADS=1 run sp1 $FEA/ccxenv/bin/ccx -i sp1
cp base.inp sp2.inp; OMP_NUM_THREADS=2 run sp2 $FEA/ccxenv/bin/ccx -i sp2
cp base.inp px2.inp; OMP_NUM_THREADS=2 run px2 /usr/lib/wine/wine64 $FEA/dhondtwin/calculix_2.23_4win/ccx_static.exe -i px2
sed 's/^\*STATIC$/*STATIC,SOLVER=PARDISO/' base.inp > pd.inp; cp $FEA/winrun_pardiso/*.dll . ; cp $FEA/winrun_pardiso/ccx_dynamic.exe .
OMP_NUM_THREADS=2 MKL_THREADING_LAYER=SEQUENTIAL run pd /usr/lib/wine/wine64 ./ccx_dynamic.exe -i pd
sed 's/^\*STATIC$/*STATIC,SOLVER=ITERATIVE CHOLESKY/' base.inp > it2.inp; OMP_NUM_THREADS=2 run it2 $FEA/ccxenv/bin/ccx -i it2
