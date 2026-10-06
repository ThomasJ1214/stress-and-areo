import os, subprocess, time, sys
CCX = "../ccxenv/bin/ccx"
def run(job, threads=2):
    env = dict(os.environ, OMP_NUM_THREADS=str(threads), CCX_NPROC_EQUATION_SOLVER=str(threads))
    t0 = time.perf_counter()
    p = subprocess.Popen([CCX, "-i", job], stdout=open(job + ".out", "w"), stderr=subprocess.STDOUT, env=env)
    _, status, ru = os.wait4(p.pid, 0)
    dt = time.perf_counter() - t0
    print(f"{job}: rc={os.waitstatus_to_exitcode(status)} wall={dt:.2f}s cpu={ru.ru_utime + ru.ru_stime:.2f}s maxrss={ru.ru_maxrss/1024:.0f} MB", flush=True)
for j in sys.argv[1:]:
    run(j)
