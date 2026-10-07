"""Scripting API for AutoGrip, meant for agents and scripts (e.g. the Blender MCP's
execute-code tool). None of these functions rely on the current selection. All of them
take the armature object (or its name) and return JSON-serializable dicts.

    from autogrip import api   # or bl_ext.user_default.autogrip when installed as an extension
    api.auto_grip("Armature", "Cup", side="R")
"""

import math

import bpy
from mathutils.bvhtree import BVHTree

from . import handrig as hr

SIDES = ('L', 'R')
RIG_TYPES = {'MHX': hr.makehuman_dictionary, 'RFY': hr.rigify_dictionary, 'ARP': hr.autorig_dictionary, 'FPS': hr.fps_dictionary, 'GEN': {}}


def _object(ref, kind):
    obj = bpy.data.objects.get(ref) if isinstance(ref, str) else ref
    if obj is None:
        raise ValueError("Object not found: {}".format(ref))
    if kind == 'ARMATURE' and obj.type != 'ARMATURE':
        raise ValueError("{} is not an armature".format(obj.name))
    if kind == 'MESH' and obj.type != 'MESH':
        raise ValueError("{} is not a mesh".format(obj.name))
    return obj


def _activate(armature):
    # handrig.py works on module globals and bpy.ops, so bind them to this armature
    arm = _object(armature, 'ARMATURE')
    if getattr(bpy.context, 'object', None) is not None and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    return arm


def _sides(side):
    side = side.upper()
    if side == 'BOTH':
        return list(SIDES)
    if side not in SIDES:
        raise ValueError("side must be 'L', 'R' or 'BOTH'")
    return [side]


def _flag(arm, side):
    return hr.prefix + 'hand_' + side


def _is_setup(arm, side):
    return bool(arm.data.get(_flag(arm, side), False))


def _fingers(arm, side):
    # Rebuilds the finger chains of an already set up hand
    fingers = hr.assemble_hand(arm, hr.find_hand_root(arm, side))
    for f in fingers:
        f.reconstruct()
    return [f for f in fingers if f.control_bone is not None]


def detect_rig_type(armature):
    """Returns 'MHX', 'RFY' or 'ARP' if the armature has all that rig's hand bones, else None."""
    arm = _object(armature, 'ARMATURE')
    for name, dictionary in RIG_TYPES.items():
        if all(key in arm.pose.bones for key in dictionary):
            return name
    return None


def status(armature):
    """Rig type, which hands are set up, and their grip targets."""
    arm = _object(armature, 'ARMATURE')
    return {
        "armature": arm.name,
        "rig_type": arm.global_rig_choice,
        "detected_rig_type": detect_rig_type(arm),
        "hands": {s: {"setup": _is_setup(arm, s), "target": arm.data.get(hr.prefix + 'target_' + s)}
                  for s in SIDES},
    }


def setup(armature, side='BOTH', rig_type='AUTO'):
    """Builds projectors, IK, drivers and control bones. rig_type: 'AUTO', 'MHX', 'RFY' or 'ARP'.
    With side='BOTH' a hand the rig doesn't have is skipped instead of failing."""
    arm = _activate(armature)
    if rig_type == 'AUTO':
        rig_type = detect_rig_type(arm)
        if rig_type is None:
            raise RuntimeError("Rig type not recognised. Pass rig_type='MHX', 'RFY' or 'ARP' explicitly.")
    elif rig_type not in RIG_TYPES:
        raise ValueError("rig_type must be AUTO, MHX, RFY or ARP")
    arm.global_rig_choice = rig_type

    done, skipped = [], {}
    for s in _sides(side):
        if _is_setup(arm, s):
            skipped[s] = "already set up"
            continue
        try:
            hr.setup_hand(arm, hr.find_hand_root(arm, s))
        except RuntimeError as e:
            if side.upper() != 'BOTH':
                raise
            skipped[s] = str(e)
            continue
        arm.data[_flag(arm, s)] = True
        done.append(s)
    return {"rig_type": rig_type, "setup": done, "skipped": skipped}


def set_target(armature, target, side='BOTH'):
    """Points every shrinkwrap projector of the hand(s) at a mesh object."""
    arm = _activate(armature)
    target = _object(target, 'MESH')
    sides = _sides(side)
    for s in sides:
        if not _is_setup(arm, s):
            raise RuntimeError("Hand {} is not set up. Call setup() first.".format(s))
    for s in sides:
        for f in _fingers(arm, s):
            f.target_shrinkwraps(target)
        arm.data[hr.prefix + 'target_' + s] = target.name
    return {"target": target.name, "sides": sides}


def quick_pose(armature, side='BOTH', thumb=True):
    """Closes every finger fully (90 degrees) and guesses the thumb position. No contact checks."""
    arm = _activate(armature)
    posed = []
    for s in _sides(side):
        if _is_setup(arm, s):
            hr.close_hand_fully(s, thumb)
            posed.append(s)
    return {"posed": posed}


def _touching(arm, finger, bvh, to_local, scale, tolerance):
    # True when a phalange tip is within tolerance * phalange length of the target surface
    for pb in finger.phalanges:
        tip = to_local @ (arm.matrix_world @ pb.tail)
        location, _, _, dist = bvh.find_nearest(tip)
        if location is not None and dist * scale <= tolerance * pb.length * arm.matrix_world.to_scale()[0]:
            return True
    return False


def grip(armature, side='BOTH', amount=1.0, contact=True, thumb=True, tolerance=0.35, steps=24):
    """Closes the fingers. amount 0..1 scales the maximum curl (1 = 90 degrees).
    With contact=True each finger stops as soon as a phalange tip reaches the target surface,
    so it doesn't over-close. tolerance is the contact distance as a fraction of phalange length.
    Returns each finger's final angle in degrees and whether it touched."""
    arm = _activate(armature)
    amount = max(0.0, min(1.0, amount))
    max_angle = math.pi / 2 * amount
    result = {}

    for s in _sides(side):
        if not _is_setup(arm, s):
            if side.upper() != 'BOTH':
                raise RuntimeError("Hand {} is not set up. Call setup() first.".format(s))
            continue

        bvh = to_local = scale = None
        target = bpy.data.objects.get(arm.data.get(hr.prefix + 'target_' + s, ''))
        if contact and target is not None:
            depsgraph = bpy.context.evaluated_depsgraph_get()
            bvh = BVHTree.FromObject(target, depsgraph)
            to_local = target.matrix_world.inverted()
            scale = target.matrix_world.to_scale()[0]

        fingers = _fingers(arm, s)
        if thumb:
            hr.apply_thumb_preset(arm, hr.find_hand_root(arm, s), s)
        out = {}
        for f in fingers:
            cb = f.control_bone
            cb.rotation_mode = 'XYZ'
            angle, touched = max_angle, False
            if bvh is not None:
                for i in range(1, steps + 1):
                    cb.rotation_euler[0] = max_angle * i / steps
                    bpy.context.view_layer.update()
                    if _touching(arm, f, bvh, to_local, scale, tolerance):
                        angle, touched = cb.rotation_euler[0], True
                        break
            cb.rotation_euler[0] = angle
            out[f.name] = {"angle_deg": round(math.degrees(angle), 1), "touched": touched}
        bpy.context.view_layer.update()
        result[s] = out
    return result


def release(armature, side='BOTH'):
    """Opens the fingers again (control bones back to 0). The rig stays set up."""
    arm = _activate(armature)
    opened = []
    for s in _sides(side):
        if _is_setup(arm, s):
            for f in _fingers(arm, s):
                f.control_bone.rotation_euler[0] = 0.0
            opened.append(s)
    bpy.context.view_layer.update()
    return {"released": opened}



def fix_bone_rolls(armature, side='BOTH'):
    """Fixes bone rolls for the defined finger bones of the hand(s)."""
    arm = _activate(armature)
    fixed = []
    
    if arm.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
        
    for s in _sides(side):
        try:
            root = hr.find_hand_root(arm, s)
        except RuntimeError:
            continue
            
        fingers = hr.assemble_hand(arm, root)
        
        bone_names = []
        for f in fingers:
            bone_names.append(f.palmroot.name)
            for pb in f.phalanges:
                bone_names.append(pb.name)
                
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.armature.select_all(action='DESELECT')
        
        for name in bone_names:
            if name in arm.data.edit_bones:
                arm.data.edit_bones[name].select = True
                
        bpy.ops.armature.calculate_roll(type='GLOBAL_POS_Z')
        bpy.ops.object.mode_set(mode='OBJECT')
        
        fixed.append(s)
        
    return {"fixed_rolls": fixed}

def auto_grip(armature, target, side='BOTH', rig_type='AUTO', **grip_options):
    """One call: sets up the hand(s) if needed, targets the mesh and closes the fingers on it."""
    arm = _activate(armature)
    sides = _sides(side)
    setup(arm, side, rig_type)
    sides = [s for s in sides if _is_setup(arm, s)]
    if not sides:
        raise RuntimeError("No hand could be set up on {}".format(arm.name))
    for s in sides:
        set_target(arm, target, s)
        release(arm, s)
    return grip(arm, ''.join(sides) if len(sides) == 1 else 'BOTH', **grip_options)


def reset(armature, side='BOTH', reset_pose=True):
    """Removes everything AutoGrip added to the hand(s) and, with reset_pose, the finger rotations."""
    arm = _activate(armature)
    cleared = []
    for s in _sides(side):
        if not _is_setup(arm, s):
            continue
        hr.reset_hand(arm, hr.find_hand_root(arm, s), reset_pose)
        arm.data[_flag(arm, s)] = False
        if hr.prefix + 'target_' + s in arm.data:
            del arm.data[hr.prefix + 'target_' + s]
        cleared.append(s)
    return {"reset": cleared}
