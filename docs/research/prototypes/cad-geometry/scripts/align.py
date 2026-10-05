"""Fit an imported part to an OpenRocket component envelope.

Inputs : a closed outer-skin mesh of the part (any pose, unknown units), the OR component's
         outer radius R_or, length L_or and (optionally) its radius profile r_or(s), s from fore end.
Outputs: unit scale, axis direction & point, radius, axial extent, rigid transform into the rocket
         frame (+X aft, origin at the component's fore end), diagnostics and ambiguity flags.
"""
import numpy as np

UNIT_CANDIDATES = {"mm": 1.0, "in": 25.4, "m": 1000.0, "cm": 10.0, "ft": 304.8}


def principal_axes(mesh):
    """Inertia eigen-decomposition (unit density) about the CG of a watertight mesh."""
    I = mesh.moment_inertia
    w, v = np.linalg.eigh(I)
    return mesh.center_mass, w, v


def symmetry_axis_from_inertia(w, v):
    """Body of revolution => two equal principal moments. Pick the distinct one."""
    l1, l2, l3 = w
    d12, d23 = (l2 - l1) / l2, (l3 - l2) / l3
    if d23 <= d12:     # prolate (slender): unique smallest moment
        return v[:, 0], dict(kind="prolate", distinct=d12, degeneracy=d23)
    return v[:, 2], dict(kind="oblate", distinct=d23, degeneracy=d12)


def refine_axis_from_normals(mesh, a0, side_cos=0.35, iters=3):
    """Side faces of a surface of revolution have normals perpendicular to the axis:
    minimise sum w (n.a)^2  -> smallest eigenvector of the area-weighted normal covariance."""
    n, A = mesh.face_normals, mesh.area_faces
    good = (A > 1e-12 * A.max()) & (np.linalg.norm(n, axis=1) > 0.5)   # drop degenerate (e.g. apex) faces
    n, A = n[good], A[good]
    a = a0 / np.linalg.norm(a0)
    for _ in range(iters):
        side = np.abs(n @ a) < side_cos
        C = (n[side] * A[side, None]).T @ n[side]
        w, v = np.linalg.eigh(C)
        a_new = v[:, 0] * np.sign(v[:, 0] @ a)
        a = a_new
    return a


def axis_point_from_normals(mesh, a, side_cos=0.9, trim=0.25, iters=4):
    """Normals of a surface of revolution pass through the axis. Least-squares intersection of
    the normal lines (in the plane perpendicular to a), with trimmed re-fit to reject protrusions."""
    P, n, A = mesh.triangles_center, mesh.face_normals, mesh.area_faces
    good = (A > 1e-12 * A.max()) & (np.linalg.norm(n, axis=1) > 0.5)
    P, n, A = P[good], n[good], A[good]
    side = np.abs(n @ a) < side_cos
    P, n, A = P[side], n[side], A[side]
    Pa = np.eye(3) - np.outer(a, a)
    n = (Pa @ n.T).T; n /= np.linalg.norm(n, axis=1)[:, None]
    keep = np.ones(len(P), bool)
    x = None
    for _ in range(iters):
        M = np.zeros((3, 3)); b = np.zeros(3)
        for p_, n_, w_ in zip(P[keep], n[keep], A[keep]):
            Q = Pa - np.outer(n_, n_)          # projector orthogonal to both axis and normal line
            M += w_ * Q; b += w_ * Q @ p_
        M += np.outer(a, a) * M.trace()        # fix the free coordinate along the axis
        x = np.linalg.solve(M, b + np.outer(a, a) @ P[keep].mean(0) * M.trace())
        d = P - x
        dn = np.einsum('ij,ij->i', d, n)[:, None] * n
        resid = np.linalg.norm(d - dn - np.outer(d @ a, a), axis=1)  # distance of normal line to axis point
        thr = np.quantile(resid, 1 - trim)
        keep = resid <= max(thr, 1e-9)
    return x, dict(n_side=int(side.sum()), resid_med=float(np.median(resid)))


def radius_and_extent(mesh, a, x0):
    d = mesh.vertices - x0
    s = d @ a
    r = np.linalg.norm(d - np.outer(s, a), axis=1)
    # dominant radius: area-weighted median radius of side faces
    n = mesh.face_normals; side = np.abs(n @ a) < 0.2
    fc = mesh.triangles_center[side] - x0
    rf = np.linalg.norm(fc - np.outer(fc @ a, a), axis=1)
    order = np.argsort(rf); cw = np.cumsum(mesh.area_faces[side][order])
    r_med = rf[order][np.searchsorted(cw, cw[-1] / 2)]
    return dict(s_min=float(s.min()), s_max=float(s.max()), r_max=float(r.max()), r_dominant=float(r_med))


def infer_unit(length_native, radius_native, L_or_mm, R_or_mm, tol=0.15):
    """Pick the unit whose scale makes (L, R) closest to the OR component (log error)."""
    scores = {}
    for u, s in UNIT_CANDIDATES.items():
        scores[u] = abs(np.log(length_native * s / L_or_mm)) + abs(np.log(radius_native * s / R_or_mm))
    best = min(scores, key=scores.get)
    ok = scores[best] < 2 * np.log(1 + tol)
    return best, UNIT_CANDIDATES[best], scores, ok


def rotation_to_x(a):
    """Minimal rotation taking unit vector a to +X (Rodrigues)."""
    ex = np.array([1.0, 0, 0])
    v = np.cross(a, ex); c = float(a @ ex)
    if np.linalg.norm(v) < 1e-12:
        return np.eye(3) if c > 0 else np.diag([-1.0, -1.0, 1.0])
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1 / (1 + c))


def profile(mesh_rocket, nst=60):
    """Max-radius profile r(s) along +X of a mesh already in rocket frame, s normalised 0..1."""
    v = mesh_rocket.vertices
    x = v[:, 0]; r = np.hypot(v[:, 1], v[:, 2])
    edges = np.linspace(x.min(), x.max(), nst + 1)
    idx = np.clip(np.digitize(x, edges) - 1, 0, nst - 1)
    prof = np.zeros(nst)
    np.maximum.at(prof, idx, r)
    return prof


def fit_to_component(mesh_native, R_or_mm, L_or_mm, x_fore_mm, r_profile_or=None, unit=None):
    """Full pipeline. Returns (4x4 transform native->rocket[mm], report)."""
    import trimesh
    rep = {}
    # 1. axis from inertia (unit-free), refined by normals
    c, w, v = principal_axes(mesh_native)
    a0, info = symmetry_axis_from_inertia(w, v)
    a = refine_axis_from_normals(mesh_native, a0)
    x0, pinfo = axis_point_from_normals(mesh_native, a)
    ext = radius_and_extent(mesh_native, a, x0)
    rep.update(inertia_axis=info, axis_point=pinfo, extent_native=ext)
    # 2. units
    if unit is None:
        u, s, scores, ok = infer_unit(ext["s_max"] - ext["s_min"], ext["r_dominant"], L_or_mm, R_or_mm)
        rep.update(unit=u, unit_scores=scores, unit_confident=bool(ok))
    else:
        u, s = unit, UNIT_CANDIDATES[unit]; rep.update(unit=u, unit_scores=None, unit_confident=True)
    # 3. rotation (axis -> +X), two candidate signs; choose by profile match if a profile is given
    cands = []
    for sign in (+1, -1):
        R = rotation_to_x(sign * a)
        T = np.eye(4); T[:3, :3] = s * R
        # translate: axis point -> y=z=0 ; fore end -> x_fore
        p0 = s * (R @ x0)
        smin = s * (ext["s_min"] if sign > 0 else -ext["s_max"])
        T[:3, 3] = np.array([x_fore_mm - p0[0] - smin, -p0[1], -p0[2]])
        m = mesh_native.copy(); m.apply_transform(T)
        score = None
        if r_profile_or is not None:
            pr = profile(m, len(r_profile_or))
            score = float(np.sqrt(np.mean((pr - r_profile_or) ** 2)))
        cands.append((score, sign, T, m))
    if r_profile_or is not None:
        cands.sort(key=lambda t: t[0])
        amb = abs(cands[0][0] - cands[1][0]) < 0.02 * R_or_mm
    else:
        amb = True
    score, sign, T, m = cands[0]
    rep.update(direction_scores=[c_[0] for c_ in cands], direction_ambiguous=bool(amb),
               roll_ambiguous=True, R_fit_mm=ext["r_dominant"] * s, R_or_mm=R_or_mm,
               dR_mm=ext["r_dominant"] * s - R_or_mm, L_fit_mm=(ext["s_max"] - ext["s_min"]) * s, L_or_mm=L_or_mm)
    return T, rep, m
