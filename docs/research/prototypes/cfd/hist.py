import csv, sys
r=list(csv.reader(open(sys.argv[1])))
h=[x.strip().strip('"') for x in r[0]]
step=int(sys.argv[2]) if len(sys.argv)>2 else 25
cols=[c for c in ['Inner_Iter','Time(sec)','relrms[Rho]','relrms[P]','rms[Rho]','rms[P]','CFz','CFx','CMy','CD','Avg CFL','Linear_Solver_Iterations'] if c in h]
print(' '.join(f'{c:>12s}' for c in cols))
for row in r[1::step]+[r[-1]]:
    d=dict(zip(h,row)); print(' '.join(f'{float(d[c]):12.6g}' for c in cols))
