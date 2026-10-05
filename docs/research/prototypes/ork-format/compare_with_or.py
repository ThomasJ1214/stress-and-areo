"""Compare proto_parser.py model numbers with OpenRocket 24.12's own full-precision numbers (ORProbe output)."""
import sys, os, re, math, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proto_parser as pp

probe = open(sys.argv[1] if len(sys.argv) > 1 else 'orprobe/probe_all.txt').read().splitlines()
files = collections.OrderedDict(); cur = None
for line in probe:
    p = line.split('\t')
    if p[0] == 'FILE':
        cur = p[1]; files[cur] = {'comps': [], 'sims': []}
    elif p[0] == 'COMP':
        d = {'idx': int(p[1]), 'cls': p[2], 'name': p[3], 'x': float(p[4]), 'len': float(p[5]), 'n': int(p[6])}
        for kv in p[7:]:
            k, v = kv.split('='); d[k] = float(v)
        files[cur]['comps'].append(d)
    elif p[0] == 'SIM':
        d = {'i': int(p[1]), 'name': p[2]}
        for kv in p[3:]:
            k, v = kv.split('='); d[k] = float(v)
        files[cur]['sims'].append(d)

errs = collections.defaultdict(list)   # quantity -> list of (abs err, file, comp)
def rec(q, ours, theirs, f, what, rel=False):
    if theirs is None or ours is None: return
    if isinstance(theirs, float) and math.isnan(theirs): return
    e = abs(ours - theirs)
    if rel: e = e / abs(theirs) if theirs else e
    errs[q].append((e, os.path.basename(f), what, ours, theirs))

for f, data in files.items():
    path = f.replace('../', '')
    xml, meta = pp.read_container(path); doc = pp.parse_document(xml, meta)
    comps = list(doc.rocket.iter())
    if len(comps) != len(data['comps']):
        print('COUNT MISMATCH', f, len(comps), len(data['comps'])); continue
    for c, o in zip(comps, data['comps']):
        what = '%s:%s' % (c.tag, c.name)
        rec('x_abs [m]', c.x_abs(), o['x'], f, what)
        if c.tag != 'rocket':
            rec('length [m]', c.length(), o['len'], f, what)
        rec('instance count', c.instance_count(), o['n'], f, what)
        if 'fore' in o:
            rec('fore radius [m]', c.fore_radius(), o['fore'], f, what); rec('aft radius [m]', c.aft_radius(), o['aft'], f, what)
        if 'ro' in o:
            if c.tag == 'tubefinset':
                rec('ring/tube outer radius [m]', c.tubefin_outer_radius(), o['ro'], f, what)
            else:
                rec('ring/tube outer radius [m]', c.outer_radius(), o['ro'], f, what)
                rec('ring inner radius [m]', c.inner_radius(), o['ri'], f, what)
        if 'bodyr' in o:
            rec('fin body radius [m]', c.body_radius_at_fin(), o['bodyr'], f, what)
        m, xl = pp.component_mass_cg(c)
        if c.tag not in pp.ASSEMBLY_TAGS:
            rec('component mass (rel)', m, o['compmass'], f, what, rel=True)
            if o['compmass'] > 1e-9:
                rec('component cg x [m]', xl, o['compcgx'], f, what)
    cfgs = pp.flight_configurations(doc)
    for s, o in zip(doc.simulations, data['sims']):
        cid = s['conditions'].get('configid')
        cfg = next((c for c in cfgs if c['id'] == cid), None)
        active = cfg['stages_active'] if (cfg and cfg['stages_active']) else None
        M, Mx = pp.structure_mass(doc.rocket, active)
        rec('structure mass (rel)', M, o['structMass'], f, s['name'], rel=True)
        if M > 0:
            rec('structure CG [m]', Mx / M, o['structCG'], f, s['name'])
        rec('reference length [m]', pp.reference_length(doc, active), o['refLen'], f, s['name'])

print('%-28s %6s %12s %12s   worst case' % ('quantity', 'n', 'max err', 'median'))
for q, lst in errs.items():
    lst.sort(key=lambda x: -x[0])
    med = sorted(e[0] for e in lst)[len(lst)//2]
    w = lst[0]
    print('%-28s %6d %12.3e %12.3e   %s | %s ours=%.6g OR=%.6g' % (q, len(lst), w[0], med, w[1][:45], w[2][:40], w[3], w[4]))
if '-v' in sys.argv:
    for q, lst in errs.items():
        bad = [x for x in lst if x[0] > (1e-3 if 'rel' in q else 1e-6)]
        if bad:
            print('\n== %s: %d above tolerance' % (q, len(bad)))
            for b in bad[:25]: print('   %.3e %-50s %-40s ours=%.6g OR=%.6g' % b)
