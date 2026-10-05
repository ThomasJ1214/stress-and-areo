"""Python re-implementation of OpenRocket's MotorDigest (core/.../motor/MotorDigest.java)
plus RASP (.eng) and RockSim (.rse) loader digest paths (RASPMotorLoader / RockSimMotorLoader).
stdlib only."""
import hashlib, math, struct, re, xml.etree.ElementTree as ET

EPS = 1e-11
TIME_ARRAY, MASS_SPECIFIC, MASS_PER_TIME, CG_SPECIFIC, CG_PER_TIME, FORCE_PER_TIME = (
    (0, 1000), (1, 10000), (2, 10000), (3, 1000), (4, 1000), (5, 1000))

def _nxt(v):
    return v + (EPS if v > 0 else (-EPS if v < 0 else 0.0))

def _ints(vals, mult):
    out = []
    for v in vals:
        v = _nxt(v); v *= mult; v = _nxt(v)
        out.append(int(math.floor(v + 0.5)))   # Java Math.round
    return out

def digest(parts):
    """parts: list of ((order,mult), values) in increasing order."""
    h = hashlib.md5()
    for (order, mult), vals in parts:
        iv = _ints(vals, mult)
        h.update(struct.pack('>i', order)); h.update(struct.pack('>i', len(iv)))
        for x in iv:
            h.update(struct.pack('>i', x))
    return h.hexdigest()

def _eq(a, b):  # MathUtil.equals (EPSILON 1e-8 approx)
    return abs(a - b) < 1e-8

def finalize(time, thrust, *lists):
    if not time: return
    if not _eq(time[0], 0):
        time.insert(0, 0.0); thrust.insert(0, 0.0)
        for l in lists: l.insert(0, l[0])
    if _eq(time[0], 0) and len(time) > 1 and _eq(time[1], 0):
        time.pop(0); thrust.pop(0)
    i = 0
    while i < len(time) - 1:
        while i < len(time) - 1 and _eq(time[i], time[i+1]) and _eq(thrust[i], thrust[i+1]):
            time.pop(i); thrust.pop(i)
            for l in lists: l.pop(i)
        i += 1
    n = len(time) - 1
    if n >= 1 and _eq(time[n-1], time[n]):
        if _eq(thrust[n-1], 0):
            time.pop(n-1); thrust.pop(n-1)
            for l in lists: l.pop(n-1)
        elif _eq(thrust[n], 0):
            time.pop(n); thrust.pop(n)
            for l in lists: l.pop(n)

def rasp_motors(text):
    lines = text.splitlines(); i = 0; out = []
    while i < len(lines):
        while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith(';')):
            i += 1
        if i >= len(lines): break
        hdr = lines[i].split(); i += 1
        if len(hdr) != 7: raise ValueError('bad RASP header %r' % hdr)
        desig, dia, ln, delays, propw, totw, mfg = hdr
        t, f = [], []
        while i < len(lines) and not lines[i].lstrip().startswith(';'):
            p = lines[i].split(); i += 1
            if not p: continue
            t.append(float(p[0])); f.append(float(p[1]))
        pairs = sorted(zip(t, f)); t = [a for a, _ in pairs]; f = [b for _, b in pairs]
        finalize(t, f)
        tot, prop = float(totw), float(propw)
        d = digest([(TIME_ARRAY, t), (MASS_SPECIFIC, [tot, tot - prop]), (FORCE_PER_TIME, f)])
        out.append(dict(manufacturer=mfg, designation=desig, diameter=float(dia)/1000, length=float(ln)/1000,
                        time=t, thrust=f, total_mass=tot, prop_mass=prop, digest=d))
    return out

def rse_motors(text):
    root = ET.fromstring(text); out = []
    for e in root.iter('engine'):
        init = float(e.get('initWt')) / 1000; prop = float(e.get('propWt')) / 1000
        calc_m = e.get('auto-calc-mass') != '0'; calc_cg = e.get('auto-calc-cg') != '0'
        rows = []
        for p in e.iter('eng-data'):
            g = lambda k: float(p.get(k)) if p.get(k) not in (None, '') else float('nan')
            rows.append((g('t'), g('f'), g('m') / 1000, g('cg') / 1000))
        rows.sort(key=lambda r: r[0])
        t = [r[0] for r in rows]; f = [r[1] for r in rows]; m = [r[2] for r in rows]; cg = [r[3] for r in rows]
        if any(math.isnan(x) for x in m): calc_m = True
        if any(math.isnan(x) for x in cg): calc_cg = True
        finalize(t, f, m, cg)
        if any((math.isnan(x) or x < 0) for x in m): calc_m = True
        if any((math.isnan(x) or x < 0) for x in cg): calc_cg = True
        parts = [(TIME_ARRAY, t)]
        parts.append((MASS_SPECIFIC, [init, init - prop]) if calc_m else (MASS_PER_TIME, m))
        if not calc_cg: parts.append((CG_PER_TIME, cg))
        parts.append((FORCE_PER_TIME, f))
        out.append(dict(manufacturer=e.get('mfg'), designation=e.get('code'), digest=digest(parts),
                        time=t, thrust=f))
    return out
