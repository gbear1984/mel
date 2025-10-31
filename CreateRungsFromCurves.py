import maya.cmds as cmds
import maya.api.OpenMaya as om
import math

def _fn_from(node):
    if cmds.nodeType(node) == 'nurbsCurve':
        shape = node
    else:
        shape = (cmds.listRelatives(node, s=True, ni=True, f=True) or [None])[0]
    if not shape: raise RuntimeError("No nurbsCurve under '{}'".format(node))
    sel = om.MSelectionList(); sel.add(shape)
    return om.MFnNurbsCurve(sel.getDagPath(0))

def _point_at_len(fn, s):
    s = max(0.0, min(s, fn.length()))
    t = fn.findParamFromLength(s)
    return fn.getPointAtParam(t, om.MSpace.kWorld), t

def _point_at_frac(fn, f):
    L = fn.length()
    return _point_at_len(fn, f*L)

def _pt_tuple(p): return (p.x, p.y, p.z)

def _wrap_param_to_len(fn, s):
    """Clamp arc length to [0,L]."""
    return max(0.0, min(s, fn.length()))

def _local_min_distance_by_arclen(fn_other, ref_pt, s_center, half_window, samples=21):
    """
    Search along OTHER curve in an arc-length window [s_center - w, s_center + w]
    and return (best_point, best_s). Keeps matches local & prevents jumps.
    """
    L = fn_other.length()
    if L <= 0.0:
        return _point_at_len(fn_other, 0.0)
    w = min(half_window, 0.25 * L)
    best_d2 = 1e99
    best_p = None
    best_s = None
    for i in range(samples):
        a = -w + (2.0 * w) * (i / float(samples - 1))
        s = max(0.0, min(L, s_center + a))
        p, _t = _point_at_len(fn_other, s)
        v = p - ref_pt
        d2 = v.x * v.x + v.y * v.y + v.z * v.z  
        if d2 < best_d2:
            best_d2, best_p, best_s = d2, p, s
    return best_p, best_s

def _should_reverse(fnA, fnB):
    tests = [0.1, 0.4, 0.7, 0.9]
    da = db = 0.0
    for f in tests:
        a,_ = _point_at_frac(fnA, f)
        b1,_= _point_at_frac(fnB, f)
        b2,_= _point_at_frac(fnB, 1.0-f)
        da += (a-b1).length()
        db += (a-b2).length()
    return db < da

# ---------------- settings ----------------
spacing        = 400.0     # arc-length spacing on the reference curve (curve units)
start_offset   = 0.0       # arc-length offset before first rung
search_window  = 1.2*spacing  # local window on other curve to refine match (arc length)
samples        = 25        # samples inside the window (more = smoother, a bit slower)
target_len     = None      # e.g., 140.0 to bias toward a specific rung length (None = no bias)
target_bias    = 0.3       # 0..1 weight for length bias vs pure closest distance
group_name     = 'cross_members_GRP'
name_prefix    = 'rung'
# ------------------------------------------

sel = cmds.ls(sl=True, long=True) or []
if len(sel) != 2:
    raise RuntimeError("Select TWO NURBS curves (reference first, other second).")

fn_ref   = _fn_from(sel[0])
fn_other = _fn_from(sel[1])
Lref     = fn_ref.length()
if spacing <= 0: raise RuntimeError("spacing must be > 0")
if start_offset >= Lref: raise RuntimeError("start_offset >= curve length")

# align directions (so fractions correspond)
rev_other = _should_reverse(fn_ref, fn_other)

if not cmds.objExists(group_name):
    cmds.group(em=True, n=group_name)

# stations along ref curve
count = int(math.floor((Lref - start_offset)/spacing)) + 1
made = []

prev_s_other = None
for i in range(count):
    sA = start_offset + i*spacing
    a, tA = _point_at_len(fn_ref, sA)
    fracA = sA / Lref if Lref > 0 else 0.0
    # initial guess on other curve by fraction (direction-aware)
    guess_frac = (1.0-fracA) if rev_other else fracA
    _, t_guess = _point_at_frac(fn_other, guess_frac)
    s_guess = fn_other.length() * guess_frac

    # keep continuity: seed search near last chosen s
    if prev_s_other is not None:
        s_seed = prev_s_other + (s_guess - prev_s_other)*0.4  # blend toward guess, mostly follow continuity
    else:
        s_seed = s_guess

    # local refine by arc-length window
    pB, s_best = _local_min_distance_by_arclen(fn_other, a, s_seed, half_window=search_window, samples=samples)

    # optional: bias toward a desired rung length near target_len (keeps lengths uniform)
    if target_len is not None and target_bias > 0.0:
        # small second pass: nudge along the curve to get distance closer to target
        # try a few offsets around s_best and pick best score = (1-b)*dist + b*|dist-target|
        best_score = 1e99; bestPB = pB; bestS = s_best
        probe_offsets = [-0.5*spacing, -0.25*spacing, 0.0, 0.25*spacing, 0.5*spacing]
        for off in probe_offsets:
            s = _wrap_param_to_len(fn_other, s_best + off)
            p,_ = _point_at_len(fn_other, s)
            d = (p - a).length()
            score = (1.0 - target_bias)*d + target_bias*abs(d - target_len)
            if score < best_score:
                best_score, bestPB, bestS = score, p, s
        pB, s_best = bestPB, bestS

    crv = cmds.curve(d=1, p=[_pt_tuple(a), _pt_tuple(pB)], n="{}_{:02d}".format(name_prefix, i))
    cmds.parent(crv, group_name)
    made.append(crv)
    prev_s_other = s_best

cmds.select(made, r=True)
print("Created {} rungs with local tracking under '{}'.".format(len(made), group_name))
