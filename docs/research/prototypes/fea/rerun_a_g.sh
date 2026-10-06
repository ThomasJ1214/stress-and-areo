#!/bin/bash
cd "$(dirname "$0")"
mkdir -p logs
for h in 4 3 2; do HEL=$h ./venv/bin/python test_a_tube_buckle.py 2>&1 | grep -E "^(tube|a0|a1)" > logs/a_h${h}_clamped_qi.txt; done
HEL=3 LAYUP=0,90,0,90,90,0,90,0 TAG=xply ./venv/bin/python test_a_tube_buckle.py 2>&1 | grep -E "^(tube|a0|a1)" > logs/a_h3_clamped_xply.txt
HEL=3 BC=hinged ./venv/bin/python test_a_tube_buckle.py 2>&1 | grep -E "^(tube|a0|a1)" > logs/a_h3_hinged_qi.txt
HEL=3 ./venv/bin/python test_a_tube_buckle.py >/dev/null 2>&1   # leave clamped qi h=3 frd for rendering
NMODES=10 XI=0.1 timeout 1700 ./venv/bin/python test_g_imperfect.py > logs/g_XI0.1.txt 2>&1
echo DONE > logs/done.txt
