#!/usr/bin/env python3
"""
Prototype OpenRocket .ork parser  (research prototype, stdlib only: zipfile, gzip, xml.etree, math, json).

What it does
  * opens an .ork in any of the three container forms OpenRocket accepts
    (ZIP with rocket.ork as FIRST entry [+ decals/, preview.png, thrustcurves/*.rse],
     GZIP-compressed XML (pre-13.04 files), or plain XML)
  * builds a component tree (all 23 component element names of format 1.0..1.11)
  * resolves lengths, radii (incl. "auto" radii OpenRocket stores without a value),
    relative + absolute axial positions (rocket nose tip = x 0, +x aft), instance counts
  * lists flight configurations: motors per mount, ignition (default+override),
    stage activeness / separation, recovery deployment (default+override)
  * extracts stored simulation conditions, summary (<flightdata> attributes), warnings,
    events and the data branches (columns keyed by English FlightDataType names)
  * CROSS-CHECKS its own geometry/mass model against the numbers OpenRocket stored in the
    simulation data (reference length, dry mass, CG at t=0) and the stored summary against
    the stored time series.

All internal values are SI (m, kg, s, rad) exactly as stored in the XML, except the
documented degree fields (angleoffset, rotation, radialdirection, cant, clusterrotation,
launchrodangle, launchroddirection) which are converted to radians here.

Usage:  python3 proto_parser.py file1.ork [file2.ork ...] [--json outdir] [--quiet]
"""
import sys, os, io, re, math, json, zipfile, gzip, argparse
import xml.etree.ElementTree as ET

# ----------------------------------------------------------------------------------------
# 1. Container
# ----------------------------------------------------------------------------------------

def read_container(path):
    raw = open(path, 'rb').read()
    meta = {'path': path, 'size': len(raw), 'attachments': []}
    if raw[:2] == b'PK':
        z = zipfile.ZipFile(io.BytesIO(raw))
        infos = z.infolist()
        # OpenRocket's loader uses ONLY the first zip entry, and only if its name ends in .ork/.rkt/.cdx1
        first = infos[0].filename
        if not re.search(r'\.(ork|rkt|cdx1)$', first, re.I):
            raise ValueError('first zip entry %r is not *.ork' % first)
        meta['container'] = 'zip'
        meta['main_entry'] = first
        meta['attachments'] = [(i.filename, i.file_size) for i in infos[1:]]
        xml = z.read(first)
    elif raw[:2] == b'\x1f\x8b':
        meta['container'] = 'gzip'
        xml = gzip.decompress(raw)
    else:
        meta['container'] = 'xml'
        xml = raw
    return xml, meta


# ----------------------------------------------------------------------------------------
# 2. Value helpers
# ----------------------------------------------------------------------------------------

def fnum(s, default=None):
    if s is None:
        return default
    s = s.strip()
    if s == '':
        return default
    if s.lower() == 'nan':
        return float('nan')
    if s.lower() == 'inf':
        return float('inf')
    if s.lower() == '-inf':
        return float('-inf')
    return float(s)


def auto_num(s):
    """'auto 0.025' -> (True, 0.025); 'auto' -> (True, None); '0.025' -> (False, 0.025)."""
    if s is None:
        return (False, None)
    s = s.strip()
    if s.startswith('auto'):
        rest = s[4:].strip()
        return (True, fnum(rest) if rest else None)
    return (False, fnum(s))


def fbool(s, default=False):
    if s is None:
        return default
    return s.strip().lower() == 'true'


DEG = math.pi / 180.0
EMULATE_OR_STALE_POSITION = True   # reproduce OpenRocket's numbers exactly (see REPORT)

COMPONENT_TAGS = {
    # external
    'nosecone', 'bodytube', 'transition', 'trapezoidfinset', 'ellipticalfinset', 'freeformfinset',
    'tubefinset', 'launchlug', 'railbutton',
    # internal
    'engineblock', 'innertube', 'tubecoupler', 'bulkhead', 'centeringring',
    'masscomponent', 'shockcord', 'parachute', 'streamer',
    # assemblies
    'stage', 'boosterset', 'parallelstage', 'podset',
}
# elements inside a component that are NOT simple scalar parameters
NESTED = {'subcomponents', 'motormount', 'appearance', 'insideappearance', 'inside-appearance',
          'finpoints', 'deploymentconfiguration', 'separationconfiguration', 'motorconfiguration',
          'flightconfiguration'}
FIN_TAGS = {'trapezoidfinset', 'ellipticalfinset', 'freeformfinset'}
SYMMETRIC_TAGS = {'nosecone', 'bodytube', 'transition'}
ASSEMBLY_TAGS = {'rocket', 'stage', 'boosterset', 'parallelstage', 'podset'}
STAGE_TAGS = {'stage', 'boosterset', 'parallelstage'}
RING_TAGS = {'engineblock', 'innertube', 'tubecoupler', 'bulkhead', 'centeringring'}
MASSOBJ_TAGS = {'masscomponent', 'shockcord', 'parachute', 'streamer'}
RECOVERY_TAGS = {'parachute', 'streamer'}
MOUNT_TAGS = {'bodytube', 'innertube'}

FINISH_ROUGHNESS = {  # ExternalComponent.Finish  (m)
    'rough': 500e-6, 'roughunfinished': 250e-6, 'unfinished': 150e-6, 'normal': 60e-6,
    'smooth': 20e-6, 'optimum': 5e-6, 'polished': 2e-6, 'finishpolished': 0.5e-6, 'mirror': 0.0}
CROSS_SECTION_VOLUME = {'square': 1.00, 'rounded': 0.99, 'airfoil': 0.85}

# ClusterConfiguration.java (unit-spacing points; scaled by 2*outerRadius*clusterScale)
_R5 = 1.0 / (2 * math.sin(2 * math.pi / 10)); _S2 = math.sqrt(2); _S3 = math.sqrt(3)
def _ring(n, r):
    return [c for i in range(n) for c in (r * math.sin(2 * math.pi * i / n), r * math.cos(2 * math.pi * i / n))]
CLUSTERS = {
    'single': [0, 0], 'double': [-0.5, 0, 0.5, 0], '3-row': [-1, 0, 0, 0, 1, 0],
    '4-row': [-1.5, 0, -0.5, 0, 0.5, 0, 1.5, 0],
    '3-ring': [-0.5, -1 / (2 * _S3), 0.5, -1 / (2 * _S3), 0, 1 / _S3],
    '4-ring': [-0.5, 0.5, 0.5, 0.5, 0.5, -0.5, -0.5, -0.5],
    '5-ring': [0, _R5] + [c for i in range(1, 5) for c in (_R5 * math.sin(2 * math.pi * i / 5), _R5 * math.cos(2 * math.pi * i / 5))],
    '6-ring': [0, 1, _S3 / 2, 0.5, _S3 / 2, -0.5, 0, -1, -_S3 / 2, -0.5, -_S3 / 2, 0.5],
    '3-star': [0, 0, 0, 1, _S3 / 2, -0.5, -_S3 / 2, -0.5],
    '4-star': [0, 0, -1 / _S2, 1 / _S2, 1 / _S2, 1 / _S2, 1 / _S2, -1 / _S2, -1 / _S2, -1 / _S2],
    '5-star': [0, 0, 0, 1] + [c for i in range(1, 5) for c in (math.sin(2 * math.pi * i / 5), math.cos(2 * math.pi * i / 5))],
    '6-star': [0, 0, 0, 1, _S3 / 2, 0.5, _S3 / 2, -0.5, 0, -1, -_S3 / 2, -0.5, -_S3 / 2, 0.5],
    '9-grid': [-1.4, 1.4, 0, 1.4, 1.4, 1.4, -1.4, 0, 0, 0, 1.4, 0, -1.4, -1.4, 0, -1.4, 1.4, -1.4],
    '9-star': [0, 0, 1.4, 0, 1.4 / _S2, -1.4 / _S2, 0, -1.4, -1.4 / _S2, -1.4 / _S2, -1.4, 0, -1.4 / _S2, 1.4 / _S2, 0, 1.4, 1.4 / _S2, 1.4 / _S2],
}


# ----------------------------------------------------------------------------------------
# 3. Transition / nose-cone profile (Transition.Shape, incl. clipping) -- exact port
# ----------------------------------------------------------------------------------------

def _shape_radius(shape, x, radius, length, param):
    if shape == 'conical':
        return radius * x / length
    if shape == 'ogive':
        if length < radius:
            x = x * radius / length; length = radius
        if param < 0.001:
            return radius * x / length
        R = math.sqrt(max(0.0, (length ** 2 + radius ** 2) * (((2 - param) * length) ** 2 + (param * radius) ** 2)
                          / (4 * (param * radius) ** 2)))
        L = length / param
        y0 = math.sqrt(max(0.0, R * R - L * L))
        return math.sqrt(max(0.0, R * R - (L - x) ** 2)) - y0
    if shape == 'ellipsoid':
        x = x * radius / length
        return math.sqrt(max(0.0, 2 * radius * x - x * x))
    if shape == 'power':
        if param <= 0.00001:
            return 0.0 if x <= 0.00001 else radius
        return radius * (x / length) ** param
    if shape == 'parabolic':
        return radius * ((2 * x / length - param * (x / length) ** 2) / (2 - param))
    if shape == 'haack':
        theta = math.acos(max(-1.0, min(1.0, 1 - 2 * x / length)))
        v = theta - math.sin(2 * theta) / 2 + (param * math.sin(theta) ** 3 if param != 0 else 0.0)
        return radius * math.sqrt(max(0.0, v / math.pi))
    raise ValueError('unknown shape ' + shape)

CLIPPABLE = {'ellipsoid', 'power', 'haack'}
SHAPE_DEFAULT_PARAM = {'ogive': 1.0, 'power': 0.5, 'parabolic': 1.0, 'haack': 0.0}


# ----------------------------------------------------------------------------------------
# 4. Component model
# ----------------------------------------------------------------------------------------

class Component:
    def __init__(self, tag, parent=None):
        self.tag = tag
        self.parent = parent
        self.children = []
        self.p = {}        # element -> text (LAST occurrence wins, like OpenRocket's setters)
        self.pa = {}       # element -> attributes of last occurrence
        self.multi = {}    # element -> list of (attrs, text) for repeated elements
        self.unknown = []
        self.motormount = None
        self.finpoints = None
        self.deploy_overrides = {}
        self.separation_overrides = {}
        self.flightconfigs = []       # rocket only
        self.appearance = None
        self.preset = None
        self._cache = {}

    # ---- basic accessors
    def g(self, k, d=None):
        return self.p.get(k, d)

    def num(self, k, d=None):
        v = self.p.get(k)
        return fnum(v, d) if v is not None else d

    @property
    def name(self):
        return self.g('name', self.tag)

    @property
    def id(self):
        return self.g('id')

    def path(self):
        n, c = [], self
        while c is not None:
            n.append(c.name); c = c.parent
        return '/'.join(reversed(n))

    def iter(self):
        yield self
        for ch in self.children:
            yield from ch.iter()

    # ---- axial positioning (RocketComponent.setAxialOffset / setAfter / AxialMethod)
    @property
    def axial_method(self):
        if 'axialoffset' in self.pa:
            m = self.pa['axialoffset'].get('method')
        elif 'position' in self.pa:          # pre-1.8 name, attribute 'type'
            m = self.pa['position'].get('type')
        else:
            return 'after'
        return (m or 'after').strip().lower()

    @property
    def axial_offset(self):
        if 'axialoffset' in self.p:
            return fnum(self.p['axialoffset'], 0.0)
        if 'position' in self.p:
            return fnum(self.p['position'], 0.0)
        return 0.0

    # ---- instance handling
    def instance_count(self):
        t = self.tag
        if t in FIN_TAGS or t == 'tubefinset':
            return int(self.num('instancecount', self.num('fincount', 1)))
        if t in ('launchlug', 'railbutton', 'bulkhead', 'centeringring', 'podset', 'parallelstage', 'boosterset'):
            return int(self.num('instancecount', 1))
        if t == 'innertube':
            return len(CLUSTERS.get(self.g('clusterconfiguration', 'single'), [0, 0])) // 2
        return 1

    def instance_separation(self):
        return self.num('instanceseparation', 0.0)

    def angle_offset(self):
        """radians; <angleoffset> (deg) preferred, then <rotation>/<radialdirection> (deg)."""
        for k in ('angleoffset', 'rotation', 'radialdirection'):
            if k in self.p:
                return fnum(self.p[k], 0.0) * DEG
        return 0.0

    # ---- lengths (getLength)
    def length(self):
        if 'length' in self._cache:
            return self._cache['length']
        t = self.tag
        if t in ('nosecone', 'bodytube', 'transition', 'tubefinset', 'launchlug') or t in RING_TAGS:
            L = self.num('length', 0.0)
        elif t == 'trapezoidfinset' or t == 'ellipticalfinset':
            L = self.num('rootchord', 0.0)
        elif t == 'freeformfinset':
            pts = self.finpoints or [(0.0, 0.0)]
            L = pts[-1][0] - pts[0][0]
        elif t in MASSOBJ_TAGS:
            L = self.num('packedlength', 0.0)
            a, r_saved = auto_num(self.g('packedradius'))
            if a and r_saved:
                # MassObject: packed VOLUME (r_saved^2 * L_saved) is preserved; with an automatic radius the
                # length is re-derived from the parent's current radius (stale saved radius otherwise).
                r_auto = self.massobject_auto_radius()
                if r_auto and r_auto > 0:
                    L = r_saved * r_saved * L / (r_auto * r_auto)
        elif t == 'railbutton':
            L = 0.0   # RailButton.getLength() == 0 in OpenRocket
        elif t in ASSEMBLY_TAGS and t != 'rocket':
            # ComponentAssembly.updateBounds(): sum of lengths of children positioned AFTER
            L = sum(ch.length() for ch in self.children if ch.axial_method == 'after')
        else:
            L = 0.0
        self._cache['length'] = L
        return L

    def massobject_auto_radius(self):
        """MassObject.getMaxParentRadius()"""
        par = self.parent
        if par is None:
            return None
        if par.tag == 'nosecone':
            return par.fore_radius() if fbool(par.g('isflipped')) else par.aft_radius()
        if par.tag == 'transition':
            return max(par.fore_radius(), par.aft_radius())
        if par.tag == 'bodytube':
            return par.inner_radius_at(0)
        if par.tag in RING_TAGS:
            return par.inner_radius()
        return 0.0

    def packed_radius(self):
        a, r = auto_num(self.g('packedradius'))
        if a:
            ra = self.massobject_auto_radius()
            if ra:
                return ra
        return r or 0.0

    def x_rel(self):
        """front of this component relative to the front of its parent (instance 0)."""
        if 'xrel' in self._cache:
            return self._cache['xrel']
        par = self.parent
        if par is None:
            x = 0.0
        else:
            m = self.axial_method; off = self.axial_offset
            if m == 'after':
                idx = par.children.index(self)
                if idx == 0:
                    x = 0.0
                else:
                    prev = par.children[idx - 1]
                    x = prev.x_rel() + prev.length()
            elif m == 'absolute':
                x = off - par.x_abs()
            else:
                pl = 0.0 if par.tag == 'rocket' else par.length()
                L = self.length()
                if EMULATE_OR_STALE_POSITION and self.tag in MASSOBJ_TAGS and auto_num(self.g('packedradius'))[0]:
                    # OpenRocket 23.09/24.12 computes the position at load time with the SAVED packed length,
                    # but uses the auto-radius-derived length for mass/geometry afterwards (stateful quirk).
                    L = self.num('packedlength', L)
                if m == 'top':
                    x = off
                elif m == 'middle':
                    x = off + (pl - L) / 2
                elif m == 'bottom':
                    x = off + (pl - L)
                else:
                    raise ValueError('unknown axial method %r' % m)
            if abs(x) < 1e-6:
                x = 0.0
        self._cache['xrel'] = x
        return x

    def x_abs(self):
        if 'xabs' in self._cache:
            return self._cache['xabs']
        x = 0.0 if self.parent is None else self.parent.x_abs() + self.x_rel()
        self._cache['xabs'] = x
        return x

    # ---- symmetric-component radii
    def _fore_aft_stored(self):
        """(fore, aft, fore_auto, aft_auto) as STORED in the file (auto values may be stale caches)."""
        t = self.tag
        if t == 'bodytube':
            a, r = auto_num(self.g('radius'))
            r = 0.025 if r is None else r
            return (r, r, a, a)
        if t == 'nosecone':
            a, rb = auto_num(self.g('aftradius'))
            rb = 0.025 if rb is None else rb
            if fbool(self.g('isflipped')):
                return (rb, 0.0, a, False)
            return (0.0, rb, False, a)
        if t == 'transition':
            af, rf = auto_num(self.g('foreradius')); aa, ra = auto_num(self.g('aftradius'))
            return (0.025 if rf is None else rf, 0.025 if ra is None else ra, af, aa)
        return None

    def _fore_aft(self):
        """Resolved radii. 'auto' radii are re-derived from neighbours exactly like OpenRocket does at
        run time (SymmetricComponent/BodyTube/Transition auto logic), because the number stored after
        'auto' is only the cached value at save time and CAN BE STALE (seen in example files)."""
        if 'foreaft' in self._cache:
            return self._cache['foreaft']
        f, a, fa, aa = self._fore_aft_stored()
        if self.tag == 'bodytube':
            if fa:
                r, _side = bt_auto(self, set())
                f = a = r
        else:
            if fa:
                prev = prev_sym(self)
                f = (front_auto(prev, set()) if prev is not None else 0.025)
            if aa:
                nxt = next_sym(self)
                a = (rear_auto(nxt, set()) if nxt is not None else 0.025)
        res = (f, a, fa, aa)
        self._cache['foreaft'] = res
        return res

    def fore_radius(self):
        return self._fore_aft()[0]

    def aft_radius(self):
        return self._fore_aft()[1]

    def shape(self):
        return (self.g('shape', 'conical') or 'conical').strip().lower()

    def shape_param(self):
        return self.num('shapeparameter', SHAPE_DEFAULT_PARAM.get(self.shape(), 0.0))

    def thickness_sym(self):
        v = self.g('thickness', '0')
        if v.strip() == 'filled':
            return None
        return fnum(v, 0.0)

    def radius_at(self, x):
        """outer radius at x (relative to component front) for bodytube/transition/nosecone."""
        t = self.tag
        if t == 'bodytube':
            return self.fore_radius()
        L = self.length()
        r1, r2 = self.fore_radius(), self.aft_radius()
        if x < 0:
            return r1
        if x >= L:
            return r2
        if r1 == r2:
            return r1
        if r1 > r2:
            x = L - x; r1, r2 = r2, r1
        shape, param = self.shape(), self.shape_param()
        clipped = fbool(self.g('shapeclipped'), True) and shape in CLIPPABLE
        if clipped:
            clip = self._clip_length(r1, r2)
            return _shape_radius(shape, clip + x, r2, clip + L, param)
        return r1 + _shape_radius(shape, x, r2 - r1, L, param)

    def _clip_length(self, r1, r2):
        if 'clip' in self._cache:
            return self._cache['clip']
        L = self.length(); shape, param = self.shape(), self.shape_param()
        if r1 == 0 or L <= 0:
            self._cache['clip'] = 0.0; return 0.0
        lo, hi, n = 0.0, L, 0
        while _shape_radius(shape, hi, r2, hi + L, param) - r1 < 0:
            lo = hi; hi *= 2; n += 1
            if n > 10:
                break
        while True:
            c = (lo + hi) / 2
            if hi - lo < 0.0001:
                break
            if _shape_radius(shape, c, r2, c + L, param) - r1 > 0:
                hi = c
            else:
                lo = c
        self._cache['clip'] = c
        return c

    def inner_radius_at(self, x):
        """RadialParent.getInnerRadius(x) for parents of internal components."""
        t = self.tag
        if t == 'bodytube':
            th = self.thickness_sym()
            return 0.0 if th is None else max(self.fore_radius() - th, 0.0)
        if t in ('transition', 'nosecone'):
            th = self.thickness_sym()
            return 0.0 if th is None else max(self.radius_at(x) - th, 0.0)
        if t in ('innertube', 'tubecoupler'):
            return max(self.outer_radius() - self.num('thickness', 0.0), 0.0)
        return None

    # ---- ring / tube radii (ThicknessRingComponent, RadiusRingComponent, CenteringRing)
    def outer_radius(self):
        if 'ro' in self._cache:
            return self._cache['ro']
        t = self.tag
        a, v = auto_num(self.g('outerradius'))
        if a and self.parent is not None and self.parent.inner_radius_at(0) is not None:
            par = self.parent
            pos1 = min(max(self.x_rel(), 0.0), par.length())
            pos2 = min(max(self.x_rel() + self.length(), 0.0), par.length())
            v = min(par.inner_radius_at(pos1), par.inner_radius_at(pos2))
        if v is None:
            v = 0.0
        self._cache['ro'] = v
        return v

    def inner_radius(self):
        """inner radius of ring-like components."""
        t = self.tag
        ro = self.outer_radius()
        if t in ('innertube', 'tubecoupler', 'engineblock'):
            return max(ro - self.num('thickness', 0.0), 0.0)
        if t == 'bulkhead':
            return 0.0
        if t == 'centeringring':
            a, v = auto_num(self.g('innerradius'))
            if a:
                v = 0.0
                if self.parent is not None:
                    for sib in self.parent.children:
                        if sib.tag != 'innertube':
                            continue
                        p1 = self.x_abs() - sib.x_abs(); p2 = p1 + self.length()
                        if p2 < 0 or p1 > sib.length():
                            continue
                        v = max(v, sib.outer_radius())
                v = min(v, ro)
            return v or 0.0
        return 0.0

    # ---- fin geometry
    def body_radius_at_fin(self):
        par = self.parent
        if par is not None and par.tag in SYMMETRIC_TAGS:
            return par.radius_at(self.x_rel())
        return 0.0

    def fin_points(self):
        t = self.tag
        if t == 'trapezoidfinset':
            root, tip = self.num('rootchord', 0.0), self.num('tipchord', 0.0)
            sweep, h = self.num('sweeplength', 0.0), self.num('height', 0.0)
            pts = [(0.0, 0.0), (sweep, h)]
            if tip > 0.0001:
                pts.append((sweep + tip, h))
            pts.append((max(root, 0.0001), 0.0))
            return pts
        if t == 'ellipticalfinset':
            L, h, n = max(self.num('rootchord', 0.0), 0.0001), self.num('height', 0.0), 31
            pts = []
            for i in range(n):
                a = math.pi * (n - 1 - i) / (n - 1)
                pts.append(((math.cos(a) + 1) / 2 * L, math.sin(a) * h))
            pts[0] = (0.0, 0.0); pts[-1] = (L, 0.0)
            return pts
        if t == 'freeformfinset':
            return list(self.finpoints or [])
        return []

    def tubefin_outer_radius(self):
        a, v = auto_num(self.g('radius'))
        if a:
            rb = self.body_radius_at_fin(); n = self.instance_count()
            if n < 3:
                return rb
            s = math.sin(math.pi / n)
            return rb * s / (1 - s)
        return v or 0.0

    def stage_number(self):
        c = self
        while c is not None:
            if c.tag in STAGE_TAGS:
                return c._stage_no
            c = c.parent
        return 0



# ---- auto radius chain (stateless re-implementation of OpenRocket's stateful refComp logic) ----

def _inline_sequence(c):
    """symmetric components forming the inline chain c belongs to (same parent; stages under the
    rocket are concatenated, mimicking getPrevious/NextSymmetricComponent)."""
    par = c.parent
    if par is None:
        return [c]
    if par.tag == 'stage' and par.parent is not None and par.parent.tag == 'rocket':
        seq = []
        for st in par.parent.children:
            seq += [x for x in st.children if x.tag in SYMMETRIC_TAGS]
        return seq
    return [x for x in par.children if x.tag in SYMMETRIC_TAGS]


def prev_sym(c):
    seq = _inline_sequence(c); i = seq.index(c)
    return seq[i - 1] if i > 0 else None


def next_sym(c):
    seq = _inline_sequence(c); i = seq.index(c)
    return seq[i + 1] if i + 1 < len(seq) else None


def front_auto(c, guard):
    """SymmetricComponent.getFrontAutoRadius(): radius c offers to the NEXT component (-1 = none)."""
    f, a, fa, aa = c._fore_aft_stored()
    if c.tag == 'bodytube':
        if fa:
            p = prev_sym(c)
            return front_auto(p, guard) if p is not None else -1
        return f
    return -1 if aa else c.aft_radius()


def rear_auto(c, guard):
    """getRearAutoRadius(): radius c offers to the PREVIOUS component."""
    f, a, fa, aa = c._fore_aft_stored()
    if c.tag == 'bodytube':
        if fa:
            n = next_sym(c)
            return rear_auto(n, guard) if n is not None else -1
        return f
    return -1 if fa else c.fore_radius()


def uses_next(c, guard):
    f, a, fa, aa = c._fore_aft_stored()
    if c.tag == 'bodytube':
        return fa and bt_auto(c, guard)[1] == 'next'
    return aa


def uses_prev(c, guard):
    f, a, fa, aa = c._fore_aft_stored()
    if c.tag == 'bodytube':
        return fa and bt_auto(c, guard)[1] == 'prev'
    return fa


def bt_auto(bt, guard):
    """BodyTube.getAutoOuterRadius() -> (radius, side used). Cycles resolve like a fresh refComp=null."""
    if id(bt) in guard:
        return (-1, None)
    guard = guard | {id(bt)}
    p, n = prev_sym(bt), next_sym(bt)
    if p is not None and not uses_next(p, guard):
        r = front_auto(p, guard)
        if r >= 0:
            return (r, 'prev')
    if n is not None and not uses_prev(n, guard):
        r = rear_auto(n, guard)
        if r >= 0:
            return (r, 'next')
    return (0.025, None)

# ----------------------------------------------------------------------------------------
# 5. XML -> tree
# ----------------------------------------------------------------------------------------

class Document:
    pass


def parse_component(el, parent, stats):
    c = Component(el.tag, parent)
    for ch in el:
        tag = ch.tag
        stats.setdefault(c.tag, {}).setdefault(tag, 0)
        stats[c.tag][tag] += 1
        if tag == 'subcomponents':
            for sub in ch:
                if sub.tag in COMPONENT_TAGS:
                    c.children.append(parse_component(sub, c, stats))
                else:
                    c.unknown.append(sub.tag)
        elif tag == 'motormount':
            c.motormount = parse_motormount(ch)
        elif tag == 'finpoints':
            c.finpoints = [(fnum(p.get('x')), fnum(p.get('y'))) for p in ch.findall('point')]
        elif tag == 'deploymentconfiguration':
            c.deploy_overrides[ch.get('configid')] = {k.tag: (k.text or '').strip() for k in ch}
        elif tag == 'separationconfiguration':
            c.separation_overrides[ch.get('configid')] = {k.tag: (k.text or '').strip() for k in ch}
        elif tag in ('motorconfiguration', 'flightconfiguration'):
            c.flightconfigs.append({
                'id': ch.get('configid'), 'default': ch.get('default') == 'true',
                'name': (ch.findtext('name') or None),
                'stages': {int(s.get('number')): s.get('active') == 'true' for s in ch.findall('stage')}})
        elif tag in ('appearance', 'insideappearance', 'inside-appearance'):
            d = {'kind': tag}
            paint = ch.find('paint')
            if paint is not None:
                d['paint'] = dict(paint.attrib)
            dec = ch.find('decal')
            if dec is not None:
                d['decal'] = dec.get('name')
            if tag == 'appearance':
                c.appearance = d
            else:
                c.inside_appearance = d
        elif tag == 'preset':
            c.preset = dict(ch.attrib)
        else:
            text = ch.text or ''
            c.p[tag] = text
            c.pa[tag] = dict(ch.attrib)
            c.multi.setdefault(tag, []).append((dict(ch.attrib), text))
    return c


def parse_motormount(el):
    mm = {'ignitionevent': 'automatic', 'ignitiondelay': 0.0, 'overhang': 0.0, 'motors': {}, 'ignition_overrides': {}}
    for ch in el:
        if ch.tag == 'ignitionevent':
            mm['ignitionevent'] = (ch.text or '').strip()
        elif ch.tag == 'ignitiondelay':
            mm['ignitiondelay'] = fnum(ch.text, 0.0)
        elif ch.tag == 'overhang':
            mm['overhang'] = fnum(ch.text, 0.0)
        elif ch.tag == 'motor':
            d = {k.tag: (k.text or '').strip() for k in ch}
            delay = d.get('delay')
            mm['motors'][ch.get('configid')] = {
                'type': d.get('type'), 'manufacturer': d.get('manufacturer'), 'designation': d.get('designation'),
                'digest': d.get('digest'), 'diameter': fnum(d.get('diameter')), 'length': fnum(d.get('length')),
                'delay': None if (delay is None or delay == 'none') else fnum(delay),  # None => plugged
                'delay_raw': delay}
        elif ch.tag == 'ignitionconfiguration':
            d = {k.tag: (k.text or '').strip() for k in ch}
            mm['ignition_overrides'][ch.get('configid')] = {'ignitionevent': d.get('ignitionevent'),
                                                             'ignitiondelay': fnum(d.get('ignitiondelay'))}
    return mm


def parse_document(xml_bytes, meta):
    root = ET.fromstring(xml_bytes)
    if root.tag != 'openrocket':
        raise ValueError('root element is %r' % root.tag)
    doc = Document()
    doc.meta = meta
    doc.version = root.get('version')
    doc.creator = root.get('creator')
    doc.schema_stats = {}
    doc.top_level = [ch.tag for ch in root]
    rk = root.find('rocket')
    doc.rocket = parse_component(rk, None, doc.schema_stats)
    # stage numbers: depth-first pre-order over AxialStage/ParallelStage (Rocket.updateStageNumbers)
    n = 0
    for c in doc.rocket.iter():
        if c.tag in STAGE_TAGS:
            c._stage_no = n; n += 1
    doc.stage_count = n
    doc.custom_expressions = []
    dt = root.find('datatypes')
    if dt is not None:
        for t in dt.findall('type'):
            doc.custom_expressions.append({k.tag: (k.text or '') for k in t})
    doc.simulations = [parse_simulation(s) for s in root.findall('simulations/simulation')]
    doc.docprefs = None
    dp = root.find('docprefs')
    if dp is not None:
        doc.docprefs = {'prefs': {p.get('key'): (p.get('type'), (p.text or '').strip()) for p in dp.findall('pref')},
                        'materials': [(m.text or '') for m in dp.findall('docmaterials/material')]}
    doc.has_photostudio = root.find('photostudio') is not None
    return doc


# ----------------------------------------------------------------------------------------
# 6. Simulations
# ----------------------------------------------------------------------------------------

# English FlightDataType names (core/src/main/resources/l10n/messages.properties) -> short key.
# OpenRocket writes the LOCALISED NAME into types="..." (FlightDataType.getName()).
TYPE_KEYS = {
    'Time': 't', 'Altitude': 'h', 'Altitude above sea level': 'h_asl', 'Vertical velocity': 'vz',
    'Total velocity': 'v', 'Vertical acceleration': 'az', 'Total acceleration': 'a',
    'Position East of launch': 'px', 'Position North of launch': 'py', 'Position upwind': 'py_upwind_old',
    'Position parallel to wind': 'px_old', 'Lateral distance': 'pl', 'Lateral direction': 'theta_l',
    'Lateral velocity': 'vl', 'Lateral acceleration': 'al', 'Latitude': 'lat', 'Longitude': 'lon',
    'Angle of attack': 'aoa', 'Roll rate': 'roll_rate', 'Pitch rate': 'pitch_rate', 'Yaw rate': 'yaw_rate',
    'Vertical orientation (zenith)': 'theta', 'Lateral orientation (azimuth)': 'phi', 'Mass': 'm',
    'Motor mass': 'mp', 'Propellant mass': 'mp', 'Longitudinal moment of inertia': 'I_long',
    'Rotational moment of inertia': 'I_rot', 'Gravitational acceleration': 'g', 'CP location': 'cp',
    'CG location': 'cg', 'Stability margin calibers': 'stability', 'Thrust': 'thrust',
    'Thrust-to-weight ratio': 'twr', 'Drag force': 'drag', 'Drag coefficient': 'cd',
    'Friction drag coefficient': 'cd_friction', 'Pressure drag coefficient': 'cd_pressure',
    'Base drag coefficient': 'cd_base', 'Axial drag coefficient': 'cd_axial',
    'Normal force coefficient': 'cn', 'Pitch moment coefficient': 'cm_pitch', 'Yaw moment coefficient': 'cm_yaw',
    'Side force coefficient': 'c_side', 'Roll moment coefficient': 'c_roll', 'Roll forcing coefficient': 'c_roll_forcing',
    'Roll damping coefficient': 'c_roll_damping', 'Pitch damping coefficient': 'c_pitch_damping',
    'Yaw damping coefficient': 'c_yaw_damping', 'Coriolis acceleration': 'a_coriolis',
    'Reference length': 'ref_len', 'Reference area': 'ref_area', 'Wind velocity': 'wind_v',
    'Wind direction': 'wind_dir', 'Air temperature': 'T', 'Air pressure': 'P', 'Air density': 'rho',
    'Speed of sound': 'a_sound', 'Mach number': 'mach', 'Reynolds number': 'Re',
    'Simulation time step': 'dt', 'Computation time': 'tc', 'Wind speed': 'wind_v',
    'Gravity': 'g',
}


# OpenRocket 26.xx (format 1.11) writes stable, language-independent save keys instead of display names,
# and renamed some display names to include a symbol suffix. Map both to the same short keys.
TYPE_KEYS.update({
    'time': 't', 'altitude': 'h', 'altitude_above_sea': 'h_asl', 'velocity_z': 'vz', 'velocity_total': 'v',
    'acceleration_z': 'az', 'acceleration_x': 'ax', 'acceleration_y': 'ay', 'acceleration_bodyx': 'abx',
    'acceleration_bodyy': 'aby', 'acceleration_bodyz': 'abz', 'acceleration_total': 'a', 'position_x': 'px',
    'position_y': 'py', 'position_xy': 'pl', 'position_direction': 'theta_l', 'velocity_xy': 'vl',
    'acceleration_xy': 'al', 'latitude': 'lat', 'longitude': 'lon', 'aoa': 'aoa', 'roll_rate': 'roll_rate',
    'pitch_rate': 'pitch_rate', 'yaw_rate': 'yaw_rate', 'orientation_theta': 'theta', 'orientation_phi': 'phi',
    'mass': 'm', 'motor_mass': 'mp', 'longitudinal_inertia': 'I_long', 'rotational_inertia': 'I_rot',
    'gravity': 'g', 'cp_location': 'cp', 'cg_location': 'cg', 'stability': 'stability',
    'damping_ratio': 'damping_ratio', 'natural_frequency': 'natural_frequency', 'mach_number': 'mach',
    'reynolds_number': 'Re', 'thrust_force': 'thrust', 'thrust_correction': 'thrust_correction',
    'thrust_weight_ratio': 'twr', 'drag_force': 'drag', 'drag_coeff': 'cd', 'friction_drag_coeff': 'cd_friction',
    'pressure_drag_coeff': 'cd_pressure', 'base_drag_coeff': 'cd_base', 'axial_drag_coeff': 'cd_axial',
    'normal_force_coeff': 'cn', 'cna': 'cna', 'pitch_moment_coeff': 'cm_pitch', 'yaw_moment_coeff': 'cm_yaw',
    'side_force_coeff': 'c_side', 'roll_moment_coeff': 'c_roll', 'roll_forcing_coeff': 'c_roll_forcing',
    'roll_damping_coeff': 'c_roll_damping', 'pitch_damping_moment_coeff': 'c_pitch_damping',
    'yaw_damping_moment_coeff': 'c_yaw_damping', 'damping_moment_coeff': 'damping_moment',
    'damping_moment_coeff_aerodynamic': 'damping_moment_aero', 'damping_moment_coeff_propulsive': 'damping_moment_prop',
    'corrective_moment_coeff': 'corrective_moment', 'coriolis_acceleration': 'a_coriolis',
    'reference_length': 'ref_len', 'reference_area': 'ref_area', 'wind_velocity': 'wind_v',
    'wind_direction': 'wind_dir', 'air_temperature': 'T', 'air_pressure': 'P', 'air_density': 'rho',
    'speed_of_sound': 'a_sound', 'time_step': 'dt', 'computation_time': 'tc',
    # symbol-suffixed English display names (26.xx dev builds)
    'Drag coefficient (CD)': 'cd', 'Friction drag coefficient (CD_friction)': 'cd_friction',
    'Pressure drag coefficient (CD_pressure)': 'cd_pressure', 'Base drag coefficient (CD_base)': 'cd_base',
    'Axial drag coefficient (CA)': 'cd_axial', 'Normal force coefficient (CN)': 'cn',
    'Normal force coefficient derivative (CN\u03b1)': 'cna', 'Normal force coefficient derivative (CNα)': 'cna',
    'Pitch moment coefficient (Cm)': 'cm_pitch', 'Damping ratio': 'damping_ratio', 'Natural frequency': 'natural_frequency',
    'Damping moment coefficient': 'damping_moment', 'Damping moment coefficient (aerodynamic)': 'damping_moment_aero',
    'Damping moment coefficient (propulsive)': 'damping_moment_prop', 'Corrective moment coefficient': 'corrective_moment',
    # simulation-extension column (RollControl example)
    'Control fin cant': 'ext_control_fin_cant',
})

def parse_simulation(el):
    s = {'status': el.get('status'), 'name': el.findtext('name'), 'simulator': el.findtext('simulator'),
         'calculator': el.findtext('calculator')}
    cond = el.find('conditions')
    c = {}
    if cond is not None:
        for ch in cond:
            if ch.tag == 'wind':
                model = ch.get('model')
                if model == 'average':
                    c['wind_average_model'] = {k.tag: fnum(k.text) for k in ch}
                elif model == 'multilevel':
                    c['wind_multilevel'] = {'altituderef': ch.get('altituderef'),
                                            'levels': [{k: fnum(v) for k, v in lv.attrib.items()} for lv in ch.findall('windlevel')]}
            elif ch.tag == 'atmosphere':
                c['atmosphere'] = {'model': ch.get('model'), **{k.tag: fnum(k.text) for k in ch}}
            else:
                c[ch.tag] = (ch.text or '').strip()
    # normalise units
    for k in ('launchrodlength', 'windaverage', 'windturbulence', 'winddirection', 'launchaltitude',
              'launchlatitude', 'launchlongitude', 'timestep', 'maxtime'):
        if k in c:
            c[k] = fnum(c[k])
    if 'launchrodangle' in c:
        c['launchrodangle_rad'] = fnum(c['launchrodangle']) * DEG
    if 'launchroddirection' in c:
        c['launchroddirection_rad'] = fnum(c['launchroddirection']) * DEG
    s['conditions'] = c
    s['extensions'] = [{'id': e.get('extensionid'), 'entries': {x.get('key'): (x.get('type'), (x.text or '').strip()) for x in e.findall('entry')}}
                       for e in el.findall('extension')]
    s['listeners'] = [(l.text or '').strip() for l in el.findall('listener')]
    fd = el.find('flightdata')
    s['flightdata'] = None
    if fd is not None:
        summ = {k: fnum(v) for k, v in fd.attrib.items()}
        warnings = []
        for w in fd.findall('warning'):
            if len(w):   # 24.12 structured
                warnings.append({'type': w.get('type'), 'id': w.findtext('id'), 'description': w.findtext('description'),
                                 'priority': w.findtext('priority'), 'sources': [x.text for x in w.findall('source')],
                                 'parameter': fnum(w.findtext('parameter'))})
            else:
                warnings.append({'type': None, 'description': (w.text or '').strip()})
        branches = []
        for b in fd.findall('databranch'):
            types = b.get('types').split(',')
            rows = []
            bad = 0
            for dp in b.findall('datapoint'):
                parts = (dp.text or '').split(',')
                if len(parts) != len(types):
                    bad += 1; continue
                rows.append([fnum(x) for x in parts])
            events = [{'time': fnum(e.get('time')), 'type': e.get('type'), 'source': e.get('source'),
                       'id': e.get('id'), 'warnid': e.get('warnid'), 'cause': e.get('cause')}
                      for e in b.findall('event')]
            cols = {}
            unknown_types = []
            for i, tname in enumerate(types):
                key = TYPE_KEYS.get(tname)
                if key is None:
                    unknown_types.append(tname); key = tname
                cols.setdefault(key, i)
            branches.append({'name': b.get('name'), 'types': types, 'cols': cols, 'rows': rows, 'events': events,
                             'bad_points': bad, 'unknown_types': unknown_types,
                             'optimumAltitude': fnum(b.get('optimumAltitude')),
                             'timeToOptimumAltitude': fnum(b.get('timeToOptimumAltitude'))})
        s['flightdata'] = {'summary': summ, 'warnings': warnings, 'branches': branches}
    return s


def col(branch, key):
    i = branch['cols'].get(key)
    if i is None:
        return None
    return [r[i] for r in branch['rows']]


def nanmax(v):
    v = [x for x in v if x is not None and not math.isnan(x)]
    return max(v) if v else float('nan')


def _interp(t, y, x):
    if not t:
        return float('nan')
    if x <= t[0]:
        return y[0]
    for k in range(1, len(t)):
        if t[k] >= x:
            if t[k] == t[k - 1]:
                return y[k]
            return y[k - 1] + (y[k] - y[k - 1]) * (x - t[k - 1]) / (t[k] - t[k - 1])
    return y[-1]


def derive_summary(sim):
    """Recompute the <flightdata> summary attributes from branch 0 exactly like
    FlightData.calculateInterestingValues(): max over branch 0; time of first max-altitude sample;
    velocities interpolated at LAUNCHROD / (last) RECOVERY_DEVICE_DEPLOYMENT / GROUND_HIT events;
    max acceleration only BEFORE the first recovery-device deployment."""
    fd = sim['flightdata']
    if not fd or not fd['branches']:
        return None
    b = fd['branches'][0]
    t, h, v, a, mach = col(b, 't'), col(b, 'h'), col(b, 'v'), col(b, 'a'), col(b, 'mach')
    out = {}
    if h:
        out['maxaltitude'] = nanmax(h)
        if t:
            i = next(k for k in range(len(h)) if h[k] == out['maxaltitude'])
            out['timetoapogee'] = t[i]
    if v:
        out['maxvelocity'] = nanmax(v)
    if mach:
        out['maxmach'] = nanmax(mach)
    if t:
        out['flighttime'] = t[-1]
    if t and a:
        dep = [e['time'] for e in b['events'] if e['type'] == 'recoverydevicedeployment']
        end = min(dep) if dep else float('inf')
        out['maxacceleration'] = max([0.0] + [a[k] for k in range(len(t)) if t[k] < end and not math.isnan(a[k])])
        out['maxacceleration_incl_recovery'] = nanmax(a)
    if t and v:
        for e in b['events']:
            if e['type'] == 'launchrod':
                out['launchrodvelocity'] = _interp(t, v, e['time'])
            elif e['type'] == 'recoverydevicedeployment':
                out['deploymentvelocity'] = _interp(t, v, e['time'])
            elif e['type'] == 'groundhit':
                out['groundhitvelocity'] = _interp(t, v, e['time'])
    return out


# ----------------------------------------------------------------------------------------
# 7. Flight configurations
# ----------------------------------------------------------------------------------------

def flight_configurations(doc):
    rocket = doc.rocket
    cfgs = []
    ids = [fc['id'] for fc in rocket.flightconfigs]
    all_comps = list(rocket.iter())   # pre-1.9 files have no <id>, so index components by tree order
    mounts = [c for c in rocket.iter() if c.motormount is not None]
    recov = [c for c in rocket.iter() if c.tag in RECOVERY_TAGS]
    stages = [c for c in rocket.iter() if c.tag in STAGE_TAGS]
    for fc in rocket.flightconfigs:
        fid = fc['id']
        motors = []
        for m in mounts:
            mm = m.motormount
            if fid in mm['motors']:
                ig = mm['ignition_overrides'].get(fid, {})
                motors.append({'mount': m.path(), 'mount_id': m.id, 'mount_index': all_comps.index(m),
                               'stage': m.stage_number(),
                               'count': m.instance_count() if m.tag == 'innertube' else 1,
                               **mm['motors'][fid],
                               'ignitionevent': ig.get('ignitionevent') or mm['ignitionevent'],
                               'ignitiondelay': ig.get('ignitiondelay') if ig.get('ignitiondelay') is not None else mm['ignitiondelay'],
                               'overhang': mm['overhang']})
        rec = []
        for r in recov:
            d = {'deployevent': r.g('deployevent', 'ejection'), 'deployaltitude': r.num('deployaltitude', 200.0),
                 'deploydelay': r.num('deploydelay', 0.0)}
            if fid in r.deploy_overrides:
                o = r.deploy_overrides[fid]
                d.update({k: (fnum(v) if k != 'deployevent' else v) for k, v in o.items()})
                d['override'] = True
            rec.append({'device': r.path(), 'id': r.id, 'type': r.tag, **d})
        seps = []
        for st in stages:
            if st._stage_no == 0:
                continue
            d = {'separationevent': st.g('separationevent', 'ejection'), 'separationdelay': st.num('separationdelay', 0.0),
                 'separationaltitude': st.num('separationaltitude', 200.0)}
            if fid in st.separation_overrides:
                o = st.separation_overrides[fid]
                d.update({k: (fnum(v) if k != 'separationevent' else v) for k, v in o.items()})
            seps.append({'stage': st.name, 'stage_no': st._stage_no, **d})
        cfgs.append({'id': fid, 'name': fc['name'], 'default': fc['default'], 'stages_active': fc['stages'],
                     'motors': motors, 'recovery': rec, 'separation': seps})
    return cfgs


# ----------------------------------------------------------------------------------------
# 8. Mass model (port of the per-component formulas + MassCalculation override logic)
# ----------------------------------------------------------------------------------------

def mat_density(c, tag='material'):
    a = c.pa.get(tag, {})
    return fnum(a.get('density'), 0.0)


def _frustum(l, r1, r2):
    vol = l * (r1 * r1 + r1 * r2 + r2 * r2)
    if vol < 1e-8:
        return l / 2, vol
    return l * (r1 * r1 + 2 * r1 * r2 + 3 * r2 * r2) / (4 * (r1 * r1 + r1 * r2 + r2 * r2)), vol


def symmetric_mass_cg(c):
    """SymmetricComponent.calculateProperties (128 frusta) + Transition shoulders."""
    L = c.length(); rho = mat_density(c)
    th = c.thickness_sym(); filled = th is None
    if c.tag == 'bodytube':
        ro = c.fore_radius(); ri = 0.0 if filled else max(ro - th, 0.0)
        return math.pi * (ro * ro - ri * ri) * L * rho, L / 2
    vol = 0.0; cgx = 0.0
    if L > 1e-8:
        N = 128
        for n in range(N):
            x1, x2 = n * L / N, (n + 1) * L / N; l = x2 - x1
            r1o, r2o = c.radius_at(x1), c.radius_at(x2)
            if filled:
                r1i = r2i = 0.0
            else:
                h = th * math.hypot(r2o - r1o, l) / l
                r1i, r2i = max(r1o - h, 0.0), max(r2o - h, 0.0)
            fcg, fv = _frustum(l, r1o, r2o); icg, iv = _frustum(l, r1i, r2i)
            dv = fv - iv
            if dv != 0:
                dcg = (fcg * fv - icg * iv) / dv
                cgx += dv * (x1 + dcg)
            vol += dv
        vol *= math.pi / 3; cgx *= math.pi / 3
    if vol < 1e-10:
        m, x = 0.0, L / 2
    else:
        m, x = rho * vol, cgx / vol
    # shoulders (Transition.calculateProperties); nose cone stores its single shoulder as aft*,
    # flipped nose cone moves it to the fore side.
    parts = [(m, x)]
    flipped = c.tag == 'nosecone' and fbool(c.g('isflipped'))
    def shoulder(prefix):
        return (c.num(prefix + 'shoulderradius', 0.0), c.num(prefix + 'shoulderlength', 0.0),
                c.num(prefix + 'shoulderthickness', 0.0), fbool(c.g(prefix + 'shouldercapped')))
    sh = {'fore': shoulder('fore'), 'aft': shoulder('aft')}
    if flipped:
        sh = {'fore': sh['aft'], 'aft': (0.0, 0.0, 0.0, False)}
    for side in ('fore', 'aft'):
        R, SL, ST, cap = sh[side]
        ir = max(R - ST, 0.0)
        if SL > 0.001:
            ms = math.pi * max(R * R - ir * ir, 0) * SL * rho
            xs = -SL / 2 if side == 'fore' else L + SL / 2
            parts.append((ms, xs))
        if cap:
            mc = math.pi * ir * ir * ST * rho
            xc = (-SL + ST - SL) / 2 if side == 'fore' else (L + SL - ST + L + SL) / 2
            parts.append((mc, xc))
    M = sum(p[0] for p in parts)
    return M, (sum(p[0] * p[1] for p in parts) / M if M > 0 else L / 2)


def _poly_centroid(pts):
    A = 0.0; cx = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]; x1, y1 = pts[(i + 1) % n]
        cr = x0 * y1 - x1 * y0
        A += cr; cx += (x0 + x1) * cr
    A /= 2
    if abs(A) < 1e-15:
        return 0.0, 0.0
    return abs(A), cx / (6 * A)


def _curve_integral(points):
    """FinSet.calculateCurveIntegral: strip integration under a closed polyline (weights may be negative)."""
    cx = cy = w = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        dx = x1 - x0
        area = dx * (y1 + y0) * 0.5
        if abs(area) < 1e-8:      # MathUtil.equals(0, area)
            continue
        common = 1.0 / (3 * (y1 + y0))
        xc = common * (x0 * (2 * y0 + y1) + x1 * (2 * y1 + y0))
        yc = common * (y1 * y0 + y1 * y1 + y0 * y0)
        nw = w + area
        if nw != 0:
            cx = (cx * w + xc * area) / nw; cy = (cy * w + yc * area) / nw
        w = nw
    return abs(w), cx, cy


def _mount_points(c, xs, xe):
    """FinSet.getMountPoints (cant offset ignored): body surface under the fin root, x relative to xs."""
    par = c.parent
    if par is None or par.tag not in SYMMETRIC_TAGS:
        return [(0.0, 0.0), (xe - xs, 0.0)]
    n = 1
    cant = c.num('cant', 0.0)
    if abs(cant) > 1e-12 or (par.tag in ('transition', 'nosecone') and par.shape() != 'conical'):
        n = min(100, int(math.ceil((xe - xs) / 0.0025)))
    n = max(n, 1)
    pts = []
    for i in range(n + 1):
        x = xs + (xe - xs) * i / n
        pts.append((x, par.radius_at(x)))
    if xs < 0 < xe:
        pts.insert(1, (0.0, pts[0][1]))
    if xs < par.length() < xe:
        pts.insert(len(pts) - 1, (par.length(), pts[-1][1]))
    return [(x - xs, y) for x, y in pts]


def fin_mass_cg(c):
    """FinSet.calculateCM: planform*thickness*crossSectionFactor + tab + fillet."""
    rho = mat_density(c); rho_f = mat_density(c, 'filletmaterial')
    t = c.num('thickness', 0.0); n = c.instance_count()
    xs_fac = CROSS_SECTION_VOLUME.get((c.g('crosssection') or 'square').strip(), 1.0)
    L = c.length()
    xf = c.x_rel()
    rf = c.body_radius_at_fin()
    mount = _mount_points(c, xf, xf + L)
    pts = c.fin_points()
    if c.tag in ('trapezoidfinset', 'ellipticalfinset') and len(mount) > 1 and pts:
        # first/last fin point snapped to the root (body) curve, relative to the fin-front radius
        pts[0] = (mount[0][0], mount[0][1] - rf)
        pts[-1] = (mount[-1][0], mount[-1][1] - rf)
    upper = [(x, y + rf) for x, y in pts]
    area, cx, cy = _curve_integral(upper + list(reversed(mount)))
    m_fin = area * t * xs_fac * rho
    parts = [(m_fin, cx)]
    th, tl = c.num('tabheight', 0.0), c.num('tablength', 0.0)
    if th * tl > 1e-10:   # FinSet.minimumTabArea; rectangle approximation (exact on straight bodies)
        rel = 'top'; off = 0.0
        for attrs, text in c.multi.get('tabposition', []):   # last <tabposition> wins
            r = attrs.get('relativeto', 'top')
            r = {'front': 'top', 'center': 'middle', 'end': 'bottom'}.get(r, r)
            rel, off = r, fnum(text, 0.0)
        front = {'top': off, 'middle': off + (L - tl) / 2, 'bottom': off + (L - tl)}.get(rel, off)
        front = max(0.0, min(front, L)); tl = max(0.0, min(tl, L - front))
        parts.append((tl * th * t * rho, front + tl / 2))
    fr = c.num('filletradius', 0.0)
    if fr > 0 and c.parent is not None and c.parent.tag in SYMMETRIC_TAGS:
        vol = 0.0; mx = 0.0
        for (x0, y0), (x1, y1) in zip(mount, mount[1:]):
            xa = (x0 + x1) / 2
            rb = c.parent.radius_at(xf + xa)
            hyp = fr + rb
            inner = math.asin(fr / hyp); outer = math.acos(fr / hyp)
            csa = 2 * (math.tan(outer) * fr * fr / 2 - outer * fr * fr / 2 - inner * rb * rb / 2)
            seg = math.hypot(x1 - x0, y1 - y0) * csa
            vol += seg; mx += seg * xa
        if vol > 0:
            parts.append((vol * rho_f, mx / vol))
    M = sum(p[0] for p in parts)
    x = sum(p[0] * p[1] for p in parts) / M if M > 0 else L / 2
    return M * n, x


def component_mass_cg(c):
    """(mass incl. own instances, cg x relative to component front)."""
    t = c.tag
    if t in SYMMETRIC_TAGS:
        return symmetric_mass_cg(c)
    if t in FIN_TAGS:
        return fin_mass_cg(c)
    if t == 'tubefinset':
        ro = c.tubefin_outer_radius(); ri = max(ro - c.num('thickness', 0.0), 0.0)
        return math.pi * (ro * ro - ri * ri) * c.length() * c.instance_count() * mat_density(c), c.length() / 2
    if t == 'launchlug':
        r = c.num('radius', 0.0); th = c.num('thickness', 0.0); n = c.instance_count(); L = c.length()
        return L * math.pi * (r * r - (r - th) ** 2) * n * mat_density(c), L / 2 + c.instance_separation() * (n - 1) / 2
    if t == 'railbutton':
        od, idd = c.num('outerdiameter', 0.0), c.num('innerdiameter', 0.0)
        H, bh, fh, sh = c.num('height', 0.0), c.num('baseheight', 0.0), c.num('flangeheight', 0.0), c.num('screwheight', 0.0)
        inner_h = H - fh - bh
        vol = math.pi * ((od / 2) ** 2 * fh + (idd / 2) ** 2 * inner_h + (od / 2) ** 2 * bh + 2.0 / 3 * (od / 2) ** 2 * sh)
        n = c.instance_count()
        return vol * n * mat_density(c), c.instance_separation() * (n - 1) / 2
    if t in RING_TAGS:
        ro, ri, L = c.outer_radius(), c.inner_radius(), c.length()
        n = c.instance_count()
        m1 = math.pi * max(ro * ro - ri * ri, 0) * L * mat_density(c)
        if t == 'innertube':
            return m1 * n, L / 2     # cluster offsets are radial only
        return m1 * n, L / 2 + c.instance_separation() * (n - 1) / 2
    if t == 'masscomponent':
        return c.num('mass', 0.0), c.length() / 2
    if t == 'shockcord':
        return c.num('cordlength', 0.0) * mat_density(c), c.length() / 2
    if t == 'parachute':
        d = c.num('diameter', 0.0)
        m = math.pi * (d / 2) ** 2 * mat_density(c) + c.num('linecount', 0) * c.num('linelength', 0.0) * mat_density(c, 'linematerial')
        return m, c.length() / 2
    if t == 'streamer':
        return c.num('striplength', 0.0) * c.num('stripwidth', 0.0) * mat_density(c), c.length() / 2
    return 0.0, c.length() / 2   # assemblies


def structure_mass(c, active_stages, mult=1.0):
    """Returns (mass, x-moment) in absolute coordinates; MassCalculation.calculateStructure semantics."""
    child_mult = mult * (c.instance_count() if (c.tag in ASSEMBLY_TAGS or c.tag == 'innertube') else 1)
    cm = cx = 0.0
    for ch in c.children:
        m, x = structure_mass(ch, active_stages, child_mult)
        cm += m; cx += x
    active = (c.tag == 'rocket') or (active_stages is None) or active_stages.get(c.stage_number(), True)
    own_m = own_x = 0.0
    if active:
        m, xl = component_mass_cg(c)
        xcm = c.x_abs() + xl
        w = m * mult
        if 'overridemass' in c.p:
            if c.tag in ASSEMBLY_TAGS:
                xcm = cx / cm if cm > 0 else c.x_abs()
            w = c.num('overridemass', 0.0) * mult
            sub = c.g('overridesubcomponentsmass')
            if sub is None:
                sub = c.g('overridesubcomponents')
            if fbool(sub):
                cm = 0.0; cx = 0.0
        if 'overridecg' in c.p:
            xcm = c.x_abs() + c.num('overridecg', 0.0)
            sub = c.g('overridesubcomponentscg')
            if sub is None:
                sub = c.g('overridesubcomponents')
            if fbool(sub):
                cx = cm * xcm
        own_m, own_x = w, w * xcm
    return own_m + cm, own_x + cx


def reference_length(doc, active_stages):
    rk = doc.rocket
    rt = (rk.g('referencetype', 'maximum') or 'maximum').strip()
    if rt == 'custom':
        return rk.num('customreference', 0.0)
    syms = [c for c in rk.iter() if c.tag in SYMMETRIC_TAGS and
            (active_stages is None or active_stages.get(c.stage_number(), True))]
    if rt == 'nosecone':
        for s in syms:
            if s.fore_radius() >= 0.0005:
                return 2 * s.fore_radius()
            if s.aft_radius() >= 0.0005:
                return 2 * s.aft_radius()
        return 0.025 * 2  # Rocket.DEFAULT_REFERENCE_LENGTH is 0.01? (only used when no body)
    r = max([max(s.fore_radius(), s.aft_radius()) for s in syms] or [0.0])
    return 2 * r


# ----------------------------------------------------------------------------------------
# 9. Report
# ----------------------------------------------------------------------------------------

def component_row(c):
    t = c.tag
    d = {'tag': t, 'name': c.name, 'id': c.id, 'depth': 0, 'method': c.axial_method, 'offset': c.axial_offset,
         'length': c.length(), 'x_rel': c.x_rel(), 'x_abs': c.x_abs(), 'instances': c.instance_count()}
    if t in SYMMETRIC_TAGS:
        d.update(fore_r=c.fore_radius(), aft_r=c.aft_radius(), thickness=c.g('thickness'), shape=c.g('shape'),
                 shape_param=c.g('shapeparameter'))
    elif t in FIN_TAGS:
        d.update(root=c.length(), height=c.num('height'), thickness=c.num('thickness'), cant_deg=c.num('cant'),
                 body_r=c.body_radius_at_fin(), cross=c.g('crosssection'), npts=len(c.fin_points()))
    elif t in RING_TAGS:
        d.update(ro=c.outer_radius(), ri=c.inner_radius(), auto_outer=auto_num(c.g('outerradius'))[0])
    elif t == 'tubefinset':
        d.update(ro=c.tubefin_outer_radius())
    elif t in MASSOBJ_TAGS:
        d.update(packedradius=c.g('packedradius'))
    if 'material' in c.pa:
        d['material'] = '%s (%s %s)' % ((c.p.get('material') or '').strip(), c.pa['material'].get('type'),
                                         c.pa['material'].get('density'))
    if 'finish' in c.p:
        d['finish'] = c.p['finish'].strip()
    for k in ('overridemass', 'overridecg', 'overridecd'):
        if k in c.p:
            d[k] = c.num(k)
    return d


def analyse(path, quiet=False):
    xml, meta = read_container(path)
    doc = parse_document(xml, meta)
    rows = []
    def walk(c, depth):
        r = component_row(c); r['depth'] = depth; rows.append(r)
        for ch in c.children:
            walk(ch, depth + 1)
    walk(doc.rocket, 0)
    cfgs = flight_configurations(doc)
    sims = []
    for s in doc.simulations:
        entry = {'name': s['name'], 'status': s['status'], 'configid': s['conditions'].get('configid'),
                 'conditions': s['conditions'], 'extensions': [e['id'] for e in s['extensions']] + s['listeners']}
        fd = s['flightdata']
        if fd:
            entry['summary'] = fd['summary']
            entry['n_warnings'] = len(fd['warnings'])
            entry['branches'] = [{'name': b['name'], 'n_points': len(b['rows']), 'n_cols': len(b['types']),
                                  'events': [(e['type'], e['time']) for e in b['events']],
                                  'unknown_types': b['unknown_types'], 'bad_points': b['bad_points']} for b in fd['branches']]
            der = derive_summary(s)
            if der:
                entry['derived_from_data'] = der
            # ---- cross-checks against our own model
            if fd['branches'] and fd['branches'][0]['rows']:
                b = fd['branches'][0]; r0 = b['rows'][0]
                cfg = next((c for c in cfgs if c['id'] == entry['configid']), None)
                active = cfg['stages_active'] if (cfg and cfg['stages_active']) else None
                chk = {}
                if 'ref_len' in b['cols']:
                    chk['ref_len_stored'] = r0[b['cols']['ref_len']]
                    chk['ref_len_model'] = reference_length(doc, active)
                if 'm' in b['cols'] and 'mp' in b['cols']:
                    m_tot, mp = r0[b['cols']['m']], r0[b['cols']['mp']]
                    M, Mx = structure_mass(doc.rocket, active)
                    chk['dry_mass_stored'] = m_tot - mp
                    chk['dry_mass_model'] = M
                    motors = [m for m in (cfg['motors'] if cfg else []) if (active is None or active.get(m['stage'], True))]
                    if 'cg' in b['cols'] and motors:
                        digests = {m['digest'] or m['designation'] for m in motors}
                        nmot = sum(m['count'] * motor_multiplicity(doc, m) for m in motors)
                        if len(digests) == 1 and nmot > 0:
                            each = mp / nmot
                            mx = 0.0
                            for m in motors:
                                mount = list(doc.rocket.iter())[m['mount_index']]
                                xm = mount.x_abs() + mount.length() - m['length'] + m['overhang'] + m['length'] / 2
                                mx += each * m['count'] * motor_multiplicity(doc, m) * xm
                            chk['cg_stored'] = r0[b['cols']['cg']]
                            chk['cg_model_motorCGatMid'] = (Mx + mx) / (M + mp) if (M + mp) > 0 else float('nan')
                            chk['cg_model_with_stored_drymass'] = (Mx / M * (m_tot - mp) + mx) / m_tot if M > 0 else float('nan')
                        else:
                            chk['cg_note'] = 'skipped: %d different motors (needs motor DB for per-motor mass)' % len(digests)
                entry['crosscheck'] = chk
        sims.append(entry)
    res = {'file': path, 'container': meta['container'], 'attachments': meta['attachments'],
           'version': doc.version, 'creator': doc.creator, 'top_level': doc.top_level,
           'rocket_name': doc.rocket.name, 'designer': doc.rocket.g('designer'), 'referencetype': doc.rocket.g('referencetype'),
           'n_components': len(rows), 'stage_count': doc.stage_count, 'components': rows,
           'flight_configurations': cfgs, 'simulations': sims, 'schema_stats': doc.schema_stats,
           'custom_expressions': doc.custom_expressions, 'docprefs': doc.docprefs}
    if not quiet:
        print_report(res)
    return res


def motor_multiplicity(doc, m):
    """number of copies of a motor mount created by ancestor assemblies (pods / boosters)."""
    mount = list(doc.rocket.iter())[m['mount_index']]
    k = 1; c = mount.parent
    while c is not None:
        if c.tag in ('podset', 'parallelstage', 'boosterset'):
            k *= c.instance_count()
        c = c.parent
    return k


def find_by_id(doc, cid):
    for c in doc.rocket.iter():
        if c.id == cid:
            return c
    raise KeyError(cid)


def print_report(r):
    print('=' * 110)
    print('%s\n  container=%s version=%s creator=%r components=%d stages=%d ref=%s' % (
        r['file'], r['container'], r['version'], r['creator'], r['n_components'], r['stage_count'], r['referencetype']))
    if r['attachments']:
        print('  attachments:', ', '.join('%s(%d)' % a for a in r['attachments']))
    print('  %-46s %-9s %9s %9s %9s %9s  %s' % ('component', 'method', 'offset', 'length', 'x_rel', 'x_abs', 'details'))
    for c in r['components']:
        det = []
        for k in ('fore_r', 'aft_r', 'ro', 'ri', 'body_r', 'shape', 'instances'):
            if k in c and c[k] is not None and not (k == 'instances' and c[k] == 1):
                v = c[k]
                det.append('%s=%s' % (k, ('%.5g' % v) if isinstance(v, float) else v))
        print('  %-46s %-9s %9.4f %9.4f %9.4f %9.4f  %s' % (('  ' * c['depth'] + '%s:%s' % (c['tag'], c['name']))[:46],
                                                         c['method'], c['offset'], c['length'], c['x_rel'], c['x_abs'], ' '.join(det)))
    for cfg in r['flight_configurations']:
        mot = '; '.join('%s %s x%d [%s] delay=%s ign=%s+%gs @%s' % (m['manufacturer'], m['designation'], m['count'], (m['digest'] or '')[:8],
                                                                  m['delay_raw'], m['ignitionevent'], m['ignitiondelay'] or 0, m['mount'].split('/')[-1])
                        for m in cfg['motors'])
        rec = '; '.join('%s:%s%s' % (x['device'].split('/')[-1], x['deployevent'],
                                       ('@%gm' % x['deployaltitude']) if x['deployevent'] == 'altitude' else '') for x in cfg['recovery'])
        print('  config %s%s name=%r stages=%s\n      motors: %s\n      recovery: %s' % (
            cfg['id'][:8], ' (default)' if cfg['default'] else '', cfg['name'], cfg['stages_active'], mot, rec))
        for s in cfg['separation']:
            print('      separation: stage %d %s +%gs' % (s['stage_no'], s['separationevent'], s['separationdelay']))
    for s in r['simulations']:
        print('  sim %r status=%s config=%s ext=%s' % (s['name'], s['status'], (s['configid'] or '')[:8], s['extensions']))
        c = s['conditions']
        print('      rod %.3fm angle %s dir %s | wind avg %s turb %s dir %s model %s | site alt %s lat %s lon %s | atm %s | dt %s maxtime %s' % (
            c.get('launchrodlength') or 0, c.get('launchrodangle'), c.get('launchroddirection'), c.get('windaverage'), c.get('windturbulence'),
            c.get('winddirection'), c.get('windmodeltype'), c.get('launchaltitude'), c.get('launchlatitude'), c.get('launchlongitude'),
            (c.get('atmosphere') or {}).get('model'), c.get('timestep'), c.get('maxtime')))
        if 'summary' in s:
            print('      stored summary:', {k: round(v, 3) for k, v in s['summary'].items()})
            for b in s['branches']:
                print('      branch %r: %d pts x %d cols; events: %s%s' % (b['name'], b['n_points'], b['n_cols'],
                                                                          ', '.join('%s@%g' % e for e in b['events'][:14]),
                                                                          ('  UNKNOWN TYPES %s' % b['unknown_types']) if b['unknown_types'] else ''))
            if 'derived_from_data' in s:
                print('      derived from data:', {k: round(v, 3) for k, v in s['derived_from_data'].items()})
            if s.get('crosscheck'):
                print('      crosscheck:', {k: (round(v, 4) if isinstance(v, float) else v) for k, v in s['crosscheck'].items()})


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--json')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args(argv)
    ok = fail = 0
    for f in a.files:
        try:
            r = analyse(f, a.quiet)
            ok += 1
            if a.json:
                os.makedirs(a.json, exist_ok=True)
                out = os.path.join(a.json, os.path.basename(os.path.dirname(f)) + '__' + os.path.basename(f) + '.json')
                json.dump(r, open(out, 'w'), indent=1, default=str)
        except Exception as e:
            import traceback; traceback.print_exc()
            print('FAILED', f, e)
            fail += 1
    print('\nparsed OK: %d   failed: %d' % (ok, fail))
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
