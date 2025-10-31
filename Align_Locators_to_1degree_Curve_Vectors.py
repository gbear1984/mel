import maya.cmds as cmds

# -------- settings --------
SOURCE_GROUPS = ['cross_members_GRP', 'cross_member_GRP']  # will use whichever exists
LOC_GROUP     = 'cross_member_locs_GRP'
AIM_AXIS      = (1, 0, 0)   # +X of locator will aim along the rung
WORLD_UP      = (0, 1, 0)   # scene/world up used by the aim
MIN_LEN       = 1e-5        # skip degenerate zero-length rungs
# --------------------------

def _curve_shape(xform):
    """Return first nurbsCurve shape under a transform or the node if it's a shape."""
    if not cmds.objExists(xform): return None
    if cmds.nodeType(xform) == 'nurbsCurve':
        return xform
    shapes = cmds.listRelatives(xform, s=True, ni=True, f=False) or []
    for s in shapes:
        if cmds.nodeType(s) == 'nurbsCurve':
            return s
    return None

def _endpoints_world(shape):
    """Return world-space endpoints (cv[0], cv[-1]) of a nurbsCurve shape."""
    cvs = cmds.ls(shape + '.cv[*]', fl=True) or []
    if len(cvs) < 2: return None, None
    p0 = cmds.pointPosition(cvs[0], w=True)
    p1 = cmds.pointPosition(cvs[-1], w=True)
    return p0, p1

def _dist2(a, b):
    dx,dy,dz = a[0]-b[0], a[1]-b[1], a[2]-b[2]
    return dx*dx + dy*dy + dz*dz

def _ensure_group(name):
    if cmds.objExists(name):
        if cmds.nodeType(name) != 'transform':
            raise RuntimeError("'{}' exists but is not a transform".format(name))
        return name
    return cmds.group(em=True, n=name)

# --- find the source group ---
src_grp = None
for g in SOURCE_GROUPS:
    if cmds.objExists(g):
        src_grp = g
        break
if not src_grp:
    raise RuntimeError("Couldn't find any of: {}".format(SOURCE_GROUPS))

# collect curve transforms under the group
children = cmds.listRelatives(src_grp, c=True, ad=True, type='transform') or []
curves = []
for x in children:
    shp = _curve_shape(x)
    if shp:
        curves.append(x)

if not curves:
    raise RuntimeError("No nurbsCurve transforms found under '{}'".format(src_grp))

# make destination group
loc_grp = _ensure_group(LOC_GROUP)

made = []
for crv in sorted(set(curves)):
    shp = _curve_shape(crv)
    if not shp: continue

    p0, p1 = _endpoints_world(shp)
    if not p0 or not p1: continue
    if _dist2(p0, p1) < MIN_LEN*MIN_LEN:
        # tiny / degenerate – skip
        continue

    # midpoint for locator position
    mid = [(p0[i] + p1[i]) * 0.5 for i in range(3)]

    # create locator
    loc = cmds.spaceLocator(n=crv.split('|')[-1] + '_LOC')[0]
    cmds.xform(loc, ws=True, t=mid)

    # build a tiny temp target at p1 to aim at
    tgt = cmds.spaceLocator(n=loc + '_aimTMP')[0]
    cmds.xform(tgt, ws=True, t=p1)

    # aim the locator so its +X points to p1 (stable world up)
    ac = cmds.aimConstraint(
        tgt, loc,
        aimVector=AIM_AXIS,
        upVector=(0, 1, 0),
        worldUpType="scene"
    )[0]

    # delete helpers/constraint, keep baked orientation
    cmds.delete(ac, tgt)

    # parent under group
    cmds.parent(loc, loc_grp)
    made.append(loc)

cmds.select(made, r=True)
print("Created {} oriented locators under '{}' from curves in '{}'.".format(len(made), loc_grp, src_grp))
