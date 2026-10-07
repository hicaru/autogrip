"""Headless smoke test. Run from the folder that contains the autogrip package folder:

    blender -b --factory-startup --python autogrip/tests/smoke.py

(For a plain git checkout, symlink or copy the repo as a folder called "autogrip".)
Builds a minimal Rigify-named hand rig and a sphere, then runs the API end to end.
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import autogrip
from autogrip import api

autogrip.register()


def build_rig():
    arm_data = bpy.data.armatures.new("Rig")
    rig = bpy.data.objects.new("Rig", arm_data)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm_data.edit_bones
    for side, sx in (('L', 1.0), ('R', -1.0)):
        hand = eb.new("DEF-hand." + side)
        hand.head, hand.tail = (sx * 1.0, 0, 0), (sx * 1.0, 0.5, 0)
        fingers = [("index", 0.00), ("middle", 0.1), ("ring", 0.2), ("pinky", 0.3)]
        for i, (name, dx) in enumerate(fingers, start=1):
            x = sx * (1.0 + dx - 0.15)
            palm = eb.new("ORG-palm.0%d.%s" % (i, side))
            palm.head, palm.tail, palm.parent = (sx * 1.0, 0.5, 0), (x, 0.8, 0), hand
            parent = palm
            for j in range(1, 4):
                b = eb.new("f_%s.0%d.%s" % (name, j, side))
                b.head, b.tail, b.parent = (x, 0.8 + 0.25 * (j - 1), 0), (x, 0.8 + 0.25 * j, 0), parent
                b.use_connect = False
                parent = b
        thumb = eb.new("ORG-thumb.01." + side)
        thumb.head, thumb.tail, thumb.parent = (sx * 1.0, 0.3, 0), (sx * 1.4, 0.5, 0), hand
        t2 = eb.new("thumb.02." + side)
        t2.head, t2.tail, t2.parent = (sx * 1.4, 0.5, 0), (sx * 1.6, 0.7, 0), thumb
        t3 = eb.new("thumb.03." + side)
        t3.head, t3.tail, t3.parent = (sx * 1.6, 0.7, 0), (sx * 1.7, 0.9, 0), t2
    bpy.ops.object.mode_set(mode='OBJECT')
    return rig


rig = build_rig()
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.4, location=(1.2, 1.3, 0.45))
ball = bpy.context.object
ball.name = "Ball"

assert api.detect_rig_type(rig) == 'RFY', api.detect_rig_type(rig)
print("SETUP", api.setup(rig, 'BOTH'))
assert all(api.status(rig)["hands"][s]["setup"] for s in "LR")
assert "AutoGrip Controls" in rig.data.collections
print("TARGET", api.set_target(rig, ball, 'L'))
print("GRIP", api.grip(rig, 'L'))
print("AUTO", api.auto_grip(rig, ball, 'R'))
print("RELEASE", api.release(rig))
print("RESET", api.reset(rig))

leftovers = [(pb.name, c.name) for pb in rig.pose.bones for c in pb.constraints if c.name.startswith("AutoGrip_")]
assert not leftovers, leftovers
assert not [b.name for b in rig.data.bones if b.name.startswith(("projector_", "control_"))]
assert not any(api.status(rig)["hands"][s]["setup"] for s in "LR")

# --- GameRig ports: fix_rotation_modes + bake_and_strip (engine-export hygiene) ---
print("SETUP2", api.setup(rig, 'BOTH'))
print("GRIP2", api.grip(rig, 'L'))
curl = api.grip_angles(rig, 'L')['L']
assert curl and any(a > 0 for a in curl.values()), curl

# fix_rotation_modes: quaternion controls are forced back to XYZ, pose preserved
for f in api._fingers(rig, 'L'):
    if f.control_bone is not None:
        f.control_bone.rotation_mode = 'QUATERNION'
fixed = api.fix_rotation_modes(rig, 'L')
assert fixed["sides"] == ["L"] and fixed["converted"], fixed
assert all(f.control_bone.rotation_mode == 'XYZ' for f in api._fingers(rig, 'L'))
assert any(a > 0 for a in api.grip_angles(rig, 'L')['L'].values()), "pose lost in conversion"
print("FIXROT", {k: (v if k != 'converted' else len(v)) for k, v in fixed.items()})

# bake_and_strip: the grip pose survives onto bare finger bones, machinery is gone
baked = api.bake_and_strip(rig, 'L', to_xyz=True)
assert baked["baked"].get('L'), baked
assert not api.status(rig)["hands"]["L"]["setup"], "L should be stripped"
assert api.status(rig)["hands"]["R"]["setup"], "R untouched by L bake"
defbones = [pb for pb in rig.pose.bones if pb.name.startswith("f_") and pb.name.endswith(".L")]
assert defbones and all(pb.rotation_mode == 'XYZ' for pb in defbones)
assert any(any(abs(v) > 1e-4 for v in pb.rotation_euler) for pb in defbones), "pose lost"
leftovers2 = [(pb.name, c.name) for pb in rig.pose.bones
              if (pb.name.endswith(".L") or pb.name in ("thumb.L",))
              for c in pb.constraints if c.name.startswith("AutoGrip_")]
assert not leftovers2, leftovers2
assert not [b.name for b in rig.data.bones
           if b.name.startswith(("projector_", "control_")) and b.name.endswith(".L")]
print("BAKE", {s: len(v) for s, v in baked["baked"].items()})
print("RESET2", api.reset(rig))

try:
    api.set_target(rig, ball, 'L')
except RuntimeError as e:
    print("expected error:", e)
else:
    raise AssertionError("set_target should fail when not set up")
print("SMOKE OK")
