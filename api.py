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
# Checked in order by detect_rig_type; 'GEN' has no required bones, so it matches
# anything and acts as the fallback. 'RFY_NO_ORG' must stay before 'GEN'.
RIG_TYPES = {'MHX': hr.makehuman_dictionary, 'RFY': hr.rigify_dictionary, 'ARP': hr.autorig_dictionary, 'FPS': hr.fps_dictionary, 'RFY_NO_ORG': hr.rigify_no_org_dictionary, 'GEN': {}}


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
    """Returns 'MHX', 'RFY', 'ARP', 'FPS' or 'RFY_NO_ORG' if the armature has all that
    rig's hand bones, else 'GEN' (the generic fallback — it has no required bones, so
    it always matches and this never returns None)."""
    arm = _object(armature, 'ARMATURE')
    for name, dictionary in RIG_TYPES.items():
        if all(key in arm.pose.bones for key in dictionary):
            return name
    return None


def status(armature):
    """Rig type, which hands are set up, their grip targets and control bone names.
    rig_type is None until setup() has run on the armature."""
    arm = _object(armature, 'ARMATURE')
    configured = any(_is_setup(arm, s) for s in SIDES)
    hands = {}
    for s in SIDES:
        if _is_setup(arm, s):
            hands[s] = {"setup": True,
                        "target": arm.data.get(hr.prefix + 'target_' + s),
                        "control_bones": [f.control_bone.name for f in _fingers(arm, s)]}
        else:
            hands[s] = {"setup": False,
                        "target": arm.data.get(hr.prefix + 'target_' + s),
                        "control_bones": []}
    return {
        "armature": arm.name,
        "rig_type": arm.global_rig_choice if configured else None,
        "detected_rig_type": detect_rig_type(arm),
        "hands": hands,
    }


def setup(armature, side='BOTH', rig_type='AUTO', projector_mirror=False, ik_gain=0.637, wrap_offset=0.15):
    """Builds projectors, IK, drivers and control bones. rig_type: 'AUTO', 'MHX', 'RFY',
    'RFY_NO_ORG', 'ARP', 'FPS' or 'GEN'. With side='BOTH' a hand the rig doesn't have is
    skipped instead of failing. projector_mirror=True flips the side of the finger the
    projectors are built on (Finger.offset += math.pi), which flips the direction the
    fingers bend in — use it when a grip closes backwards over the back of the hand.
    ik_gain scales how far the fingers fold at control 90 degrees (IK influence per
    degree): the default 0.637 stops fingers short of a full fist (good for contact on
    rounded objects); raise it towards 1.0 to wrap tightly around thin bars/cylinders.
    wrap_offset is the projector shrinkwrap distance as a fraction of projector length:
    0.15 floats the fingers just off the target surface, ~0.0 makes them hug it, small
    negative values wrap them deeper around thin grips (fingers may clip — check visually)."""
    arm = _activate(armature)
    if rig_type == 'AUTO':
        rig_type = detect_rig_type(arm)
        if rig_type is None:
            raise RuntimeError("Rig type not recognised. Pass rig_type='MHX', 'RFY', 'ARP', 'FPS' or 'GEN' explicitly.")
    elif rig_type not in RIG_TYPES:
        raise ValueError("rig_type must be one of {}".format(', '.join(RIG_TYPES)))
    arm.global_rig_choice = rig_type
    arm.data[hr.prefix + 'ik_gain'] = float(ik_gain)
    arm.data[hr.prefix + 'wrap_offset'] = float(wrap_offset)

    done, skipped = [], {}
    for s in _sides(side):
        if _is_setup(arm, s):
            skipped[s] = "already set up"
            continue
        try:
            hr.setup_hand(arm, hr.find_hand_root(arm, s), projector_mirror)
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


def wrap_projectors(armature, side='BOTH', start_deg=55.0, step_deg=65.0,
                    radius_pad=0.012, axial_pad=0.0):
    """Wraps the fingers around the current target (call set_target first).

    Repositions each projector onto the target's surface at increasing angles around the
    target's local Z axis, so the fingers fold around it like a real grip when the control
    bones close: phalange i aims start_deg + i*step_deg away from its knuckle direction,
    rotating toward the palm side. The projector shrinkwraps are disabled (they would pull
    everything back to the nearest surface point and undo the wrap). Intended for
    bar/cylinder grips: follow up with set_amount(armature, side, 1.0).
    """
    from mathutils import Vector, Matrix
    arm = _activate(armature)
    wrapped = {}
    for s in _sides(side):
        if not _is_setup(arm, s):
            if side.upper() != 'BOTH':
                raise RuntimeError("Hand {} is not set up. Call setup() first.".format(s))
            continue
        target = bpy.data.objects.get(arm.data.get(hr.prefix + 'target_' + s, ''))
        if target is None:
            raise RuntimeError("No target bound for hand {}. Call set_target() first.".format(s))
        mw = target.matrix_world
        axis = (mw.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
        center = mw.translation
        radius = target.dimensions.x / 2.0 + radius_pad
        u = axis.cross(Vector((0.0, 0.0, 1.0)))
        if u.length < 1e-4:
            u = axis.cross(Vector((1.0, 0.0, 0.0)))
        u.normalize()
        w = axis.cross(u).normalized()

        def on_surface(phi, axial):
            return center + axis * axial + (u * math.cos(phi) + w * math.sin(phi)) * radius

        out = []
        for f in _fingers(arm, s):
            palm_ref = arm.matrix_world @ f.palmroot.tail
            for p in f.projectors:
                p.constraints[hr.prefix + 'shrinkwrap'].influence = 0.0
            knuckle = arm.matrix_world @ f.phalanges[0].head
            radial = knuckle - center
            radial -= axis * radial.dot(axis)
            a0 = math.atan2(radial.dot(w), radial.dot(u))
            # rotate toward the palm: pick the sign that first approaches palm_ref's angle
            pr = palm_ref - center
            pr -= axis * pr.dot(axis)
            a_palm = math.atan2(pr.dot(w), pr.dot(u))
            d_plus = abs((a0 + math.radians(start_deg)) - a_palm + math.pi) % (2 * math.pi) - math.pi
            d_minus = abs((a0 - math.radians(start_deg)) - a_palm + math.pi) % (2 * math.pi) - math.pi
            sign = 1.0 if abs(d_plus) < abs(d_minus) else -1.0
            for i, p in enumerate(f.projectors):
                phi = a0 + sign * math.radians(start_deg + i * step_deg)
                axial = (arm.matrix_world @ p.head - center).dot(axis) + axial_pad
                goal = on_surface(phi, axial)
                bpy.context.view_layer.update()
                p.matrix = Matrix.Translation(goal) @ p.matrix.to_3x3().to_4x4()
                out.append(p.name)
        bpy.context.view_layer.update()
        wrapped[s] = out
    return wrapped


def quick_pose(armature, side='BOTH', thumb=True):
    """Closes every finger fully (90 degrees) and guesses the thumb position. No contact checks."""
    arm = _activate(armature)
    posed = []
    for s in _sides(side):
        if _is_setup(arm, s):
            hr.close_hand_fully(arm, s, thumb)
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


def _inside_bvh(bvh, to_local, world_point):
    # True when a world-space point lies inside the target mesh (its closest surface
    # normal points away from the point)
    p = to_local @ world_point
    location, normal, _, _ = bvh.find_nearest(p)
    if location is None:
        return False
    return (p - location).dot(normal) < 0.0


def grip(armature, side='BOTH', amount=1.0, contact=True, thumb=True, tolerance=0.35, steps=24):
    """Closes the fingers. amount 0..1 scales the maximum curl (1 = 90 degrees).
    With contact=True each finger stops as soon as a phalange tip reaches the target surface,
    so it doesn't over-close. tolerance is the contact distance as a fraction of phalange length.
    Returns each finger's final angle in degrees, whether it touched, and penetrated_rest
    (True when the finger was already inside the target before closing — move the target,
    it is badly placed). The per-hand dict also carries projector_side: -1 when the
    projectors sit on the palm side, 1 on the back-of-hand side (sign of the average
    projector-head minus phalange-head delta Z in world space)."""
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

        # Fingers already inside the target before any closing: the contact logic
        # would stop them instantly at tiny angles, so flag the bad target placement
        rest_penetration = {}
        if bvh is not None:
            for f in fingers:
                rest_penetration[f.name] = any(
                    _inside_bvh(bvh, to_local, arm.matrix_world @ pb.tail)
                    for pb in f.phalanges)

        # Side of the phalanges the projectors sit on (same measurement as the
        # session report's proj_delta_z): -1 = palm side, 1 = back of hand
        proj_deltas = [(arm.matrix_world @ f.projectors[0].head).z - (arm.matrix_world @ f.phalanges[0].head).z
                       for f in fingers if f.projectors]
        projector_side = -1 if (proj_deltas and sum(proj_deltas) / len(proj_deltas) < 0) else 1

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
            out[f.name] = {"angle_deg": round(math.degrees(angle), 1), "touched": touched,
                           "penetrated_rest": rest_penetration.get(f.name, False)}
        bpy.context.view_layer.update()
        out["projector_side"] = projector_side
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


def contact_sheet(frames=None, out=None, camera=None, columns=0, cell=(480, 360), engine='BLENDER_WORKBENCH', max_cells=24, focus=None, margin=1.5, orbit_deg=0):
    """Renders the given frames and composites them into a single PNG (contact sheet),
    so a whole animation can be verified from one image.

    frames: list of frame numbers, or a (start, end, step) tuple; default = scene range, thinned to max_cells.
    out: output PNG path; default 'autogrip_contact_sheet.png' next to the blend file.
    camera: camera object/name to render from; None = scene.camera (or a temp camera if the scene has none);
    'AUTO' = always build a temp camera framed on the focus bbox.
    focus: object/name to frame the temp camera on; default = all non-AutoGrip meshes.
    columns: grid columns; 0 = automatic (ceil(sqrt(n))).
    cell: (width, height) of one frame in pixels.
    engine: render engine override; BLENDER_WORKBENCH is fast and shows contact clearly.
    margin: camera distance multiplier over the fitted distance.
    orbit_deg: if nonzero and a temp camera is used, the camera orbits the focus by orbit_deg per cell,
    so every cell shows the grip from a different side.
    Returns {'out': path, 'grid': [cols, rows], 'frames': [...], 'engine': engine, 'render_log': [...]}."""
    import bpy
    import math
    import os
    import shutil
    import tempfile

    import numpy as np
    from mathutils import Vector

    scene = bpy.context.scene

    if frames is None:
        frames = list(range(scene.frame_start, scene.frame_end + 1))
        step = max(1, math.ceil(len(frames) / float(max_cells)))
        frames = frames[::step]
    elif len(frames) == 3 and all(isinstance(v, int) for v in frames):
        frames = list(range(frames[0], frames[1] + 1, frames[2]))
    if len(frames) > max_cells:
        step = math.ceil(len(frames) / float(max_cells))
        frames = frames[::step]
    if not frames:
        raise ValueError('No frames to render')

    # Camera: explicit > scene.camera > temp camera framed on the focus bbox.
    cam_obj = None
    center = None
    if camera is not None and camera != 'AUTO':
        cam_obj = _object(camera, 'CAMERA')
        if cam_obj is None:
            raise ValueError('Camera not found: {}'.format(camera))
        scene.camera = cam_obj
    if scene.camera is None or (camera == 'AUTO' and camera is not None):
        if focus is not None:
            focus_obj = _object(focus, 'MESH')
            if focus_obj is None:
                raise ValueError('Focus object not found: {}'.format(focus))
            objs = [focus_obj]
        else:
            objs = [o for o in scene.objects if o.type == 'MESH' and not o.name.startswith(hr.prefix)]
        if not objs:
            raise RuntimeError('No camera in the scene and no meshes to frame')
        mn = Vector((1e9, 1e9, 1e9))
        mx = Vector((-1e9, -1e9, -1e9))
        for o in objs:
            for c in o.bound_box:
                w = o.matrix_world @ Vector(c)
                mn = Vector((min(mn.x, w.x), min(mn.y, w.y), min(mn.z, w.z)))
                mx = Vector((max(mx.x, w.x), max(mx.y, w.y), max(mx.z, w.z)))
        center = (mn + mx) / 2
        size = max((mx - mn).length, 0.1)
        tmp_cam_data = bpy.data.cameras.new(hr.prefix + 'sheet_cam')
        cam_obj = bpy.data.objects.new(hr.prefix + 'sheet_cam', tmp_cam_data)
        scene.collection.objects.link(cam_obj)
        direction = Vector((1.0, -1.0, 0.6)).normalized()
        # fit distance from the camera's horizontal field of view
        lens = tmp_cam_data.lens
        half_fov = math.atan(tmp_cam_data.sensor_width / (2.0 * lens))
        distance = (size / 2.0) / math.tan(half_fov) * max(margin, 0.5)
        cam_obj.location = center + direction * distance
        tmp_target = bpy.data.objects.new(hr.prefix + 'sheet_target', None)
        scene.collection.objects.link(tmp_target)
        tmp_target.location = center
        track = cam_obj.constraints.new('TRACK_TO')
        track.target = tmp_target
        track.track_axis = 'TRACK_NEGATIVE_Z'
        track.up_axis = 'UP_Y'
        scene.camera = cam_obj

    w, h = cell
    old = (scene.render.engine, scene.render.resolution_x, scene.render.resolution_y,
           scene.render.resolution_percentage, scene.render.filepath)
    tmpdir = tempfile.mkdtemp(prefix='autogrip_sheet_')
    sheet_img = None
    try:
        scene.render.engine = engine
        scene.render.resolution_x = w
        scene.render.resolution_y = h
        scene.render.resolution_percentage = 100
        paths = []
        render_log = []
        orbit_center = center.copy() if center is not None else None
        orbit_base = (cam_obj.location - orbit_center).copy() if orbit_center is not None else None
        arr = np.empty(w * h * 4, dtype=np.float32)
        scene.frame_set(frames[0])
        scene.render.filepath = os.path.join(tmpdir, 'warmup.png')
        bpy.ops.render.render(write_still=True)  # warmup: first workbench render can come out black
        for i, f in enumerate(frames):
            scene.frame_set(f)
            if orbit_deg and orbit_base is not None and cam_obj.name.startswith(hr.prefix):
                from mathutils import Matrix
                ang = math.radians(orbit_deg) * i
                cam_obj.location = orbit_center + Matrix.Rotation(ang, 4, 'Z') @ orbit_base
            p = os.path.join(tmpdir, 'f%04d.png' % f)
            scene.render.filepath = p
            for attempt in range(4):
                import time
                time.sleep(0.05)
                bpy.ops.render.render(write_still=True)
                img = bpy.data.images.load(p)
                img.pixels.foreach_get(arr)
                bright = round(float(arr.max()), 3)
                ok = bright > 0.05
                bpy.data.images.remove(img)
                render_log.append({'frame': f, 'attempt': attempt + 1, 'max': bright, 'ok': ok})
                if ok:
                    break
            paths.append(p)
        cols = columns if columns else int(math.ceil(math.sqrt(len(frames))))
        rows = int(math.ceil(len(frames) / float(cols)))
        arr = np.empty(w * h * 4, dtype=np.float32)

        def composite():
            canvas = np.ones((rows * h, cols * w, 4), dtype=np.float32)
            canvas[..., :3] = 0.08
            means = []
            for i, p in enumerate(paths):
                img = bpy.data.images.load(p)
                img.pixels.foreach_get(arr)
                c, r = i % cols, i // cols
                canvas[r * h:(r + 1) * h, c * w:(c + 1) * w, :] = arr.reshape(h, w, 4)
                bpy.data.images.remove(img)
                means.append(round(float(arr.mean()), 3))
            return canvas, means

        canvas, cell_means = composite()
        # self-heal: re-render any cell that came out black and recomposite
        for round_ in range(3):
            bad = [i for i, m in enumerate(cell_means) if m < 0.05]
            if not bad:
                break
            for i in bad:
                f = frames[i]
                scene.frame_set(f)
                scene.render.filepath = paths[i]
                bpy.ops.render.render(write_still=True)
            canvas, cell_means = composite()
        out = out or os.path.join(os.path.dirname(bpy.data.filepath) or tempfile.gettempdir(),
                                  'autogrip_contact_sheet.png')
        sheet_img = bpy.data.images.new(hr.prefix + 'contact_sheet', cols * w, rows * h, alpha=False)
        sheet_img.pixels.foreach_set(canvas[::-1, :, :].ravel())  # flip: blender rows are bottom-up
        sheet_img.filepath_raw = out
        sheet_img.file_format = 'PNG'
        sheet_img.save()
    finally:
        scene.render.engine, scene.render.resolution_x, scene.render.resolution_y, \
            scene.render.resolution_percentage, scene.render.filepath = old
        if sheet_img is not None:
            bpy.data.images.remove(sheet_img)
        if camera == 'AUTO' and cam_obj is not None and cam_obj.name.startswith(hr.prefix):
            scene.camera = None
            data = cam_obj.data
            tgt = cam_obj.constraints[0].target if cam_obj.constraints else None
            bpy.data.objects.remove(cam_obj, do_unlink=True)
            if data:
                bpy.data.cameras.remove(data)
            if tgt:
                bpy.data.objects.remove(tgt, do_unlink=True)
        shutil.rmtree(tmpdir, ignore_errors=True)
    return {'out': out, 'grid': [cols, rows], 'frames': list(frames), 'engine': engine, 'render_log': render_log, 'cell_means': cell_means}


def _control_angle_deg(cb):
    # Current local X rotation of a control bone, in degrees, whatever its rotation mode
    rot = cb.rotation_euler if cb.rotation_mode == 'XYZ' else cb.rotation_quaternion.to_euler('XYZ')
    return round(math.degrees(rot[0]), 1)


def _hand_controls(arm, s):
    # Control bones of one set-up hand, with XYZ euler mode forced (drivers expect it)
    fingers = _fingers(arm, s)
    for f in fingers:
        f.control_bone.rotation_mode = 'XYZ'
    return fingers


def set_amount(armature, side='BOTH', amount=1.0):
    """Sets every control bone's local X rotation at once: amount 0..1 maps to 0..90
    degrees (the rotation limit the drivers were built with). No contact checks —
    this is the primitive quick_pose, grip and animate_grip are built on."""
    arm = _activate(armature)
    amount = max(0.0, min(1.0, amount))
    angle = math.pi / 2 * amount
    set_sides = []
    for s in _sides(side):
        if not _is_setup(arm, s):
            if side.upper() != 'BOTH':
                raise RuntimeError("Hand {} is not set up. Call setup() first.".format(s))
            continue
        for f in _hand_controls(arm, s):
            f.control_bone.rotation_euler[0] = angle
        set_sides.append(s)
    bpy.context.view_layer.update()
    return {"set": set_sides, "amount": round(amount, 3), "angle_deg": round(math.degrees(angle), 1)}


def fix_rotation_modes(armature, side='BOTH'):
    """Converts every quaternion bone of the hand rig(s) to XYZ euler, pose preserved.
    Hand-scoped port of GameRig's remove_quat_rot_mode: game engines and
    FBX/glTF exporters round-trip plain euler chains more reliably than mixed-mode
    ones. Returns {"sides": [...], "converted": [bone names that were quaternion]}"""
    arm = _activate(armature)
    converted, done = [], []
    for s in _sides(side):
        if not _is_setup(arm, s):
            if side.upper() != 'BOTH':
                raise RuntimeError("Hand {} is not set up. Call setup() first.".format(s))
            continue
        converted += hr.force_euler(arm, hr.find_hand_root(arm, s))
        done.append(s)
    bpy.context.view_layer.update()
    return {"sides": done, "converted": converted}


def bake_and_strip(armature, side='BOTH', insert_keys=False, to_xyz=False):
    """Bakes the current grip pose onto the original finger bones and removes ALL
    AutoGrip machinery (projectors, control bones, IK/shrinkwrap constraints, drivers).
    GameRig's engine-export philosophy: constraints and helper bones do not survive
    FBX/glTF export, a static bone pose does. Typical flow: setup -> set_target ->
    grip -> bake_and_strip -> export.
    insert_keys=True writes one rotation keyframe per phalange on the current frame;
    to_xyz=True additionally converts baked bones to XYZ euler (fix_rotation_modes).
    After this call the hand reads as not set up; re-run setup() to grip again."""
    arm = _activate(armature)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    baked, strips = {}, []
    for s in _sides(side):
        if not _is_setup(arm, s):
            if side.upper() != 'BOTH':
                raise RuntimeError("Hand {} is not set up. Call setup() first.".format(s))
            continue
        eval_arm = arm.evaluated_get(depsgraph)
        mats = []
        for f in _fingers(arm, s):
            for p in f.phalanges:  # root to tip order: parents bake before children
                epb = eval_arm.pose.bones.get(p.name)
                if epb is not None:
                    mats.append((p.name, epb.matrix.copy()))
        baked[s] = mats
        strips.append(s)
    if not strips:
        return {"baked": {}, "keyed": 0, "converted": 0, "machinery": "nothing was set up"}
    for s in strips:  # removes constraints, drivers, projector/control bones; keeps pose basis
        reset(arm, s, reset_pose=False)
    bpy.context.view_layer.update()  # re-evaluate WITHOUT constraints before writing back
    keyed = converted = 0
    scene = bpy.context.scene
    for s, mats in baked.items():
        for name, m in mats:
            pb = arm.pose.bones.get(name)
            if pb is None:
                continue
            pb.matrix = m  # absolute pose-space matrix, basis absorbs it
            if to_xyz and pb.rotation_mode == 'QUATERNION':
                pb.rotation_mode = 'XYZ'
                converted += 1
            if insert_keys:
                path = 'rotation_euler' if len(pb.rotation_mode) == 3 else 'rotation_quaternion'
                pb.keyframe_insert(data_path=path, frame=scene.frame_current)
                keyed += 1
    arm.update_tag()
    bpy.context.view_layer.update()
    return {"baked": {s: [n for n, _ in mats] for s, mats in baked.items()},
            "keyed": keyed, "converted": converted, "machinery": "stripped"}


def grip_angles(armature, side='BOTH'):
    """Current curl angle in degrees of every control bone of the hand(s):
    {side: {finger: angle_deg}}."""
    arm = _object(armature, 'ARMATURE')
    result = {}
    for s in _sides(side):
        if not _is_setup(arm, s):
            if side.upper() != 'BOTH':
                raise RuntimeError("Hand {} is not set up. Call setup() first.".format(s))
            continue
        result[s] = {f.name: _control_angle_deg(f.control_bone) for f in _fingers(arm, s)}
    return result


def animate_grip(armature, side='BOTH', closed_frames=(), open_frames=(), amount=1.0):
    """Keyframes a squeeze/release cycle on the control bones; the IK drivers move the
    phalanges automatically. closed_frames: frames the hand is closed (control bones at
    amount, default 1.0 = 90 degrees). open_frames: frames the hand is open (0 degrees).
    A frame in both counts as closed. Sets rotation_euler[0] keyframes on every control
    bone, e.g. animate_grip(arm, 'R', closed_frames=(13, 37, 61), open_frames=(1, 25, 49))."""
    arm = _activate(armature)
    amount = max(0.0, min(1.0, amount))
    closed = list(closed_frames)
    opened = [fr for fr in open_frames if fr not in closed]
    scene = bpy.context.scene
    current = scene.frame_current
    keyed = []
    for s in _sides(side):
        if not _is_setup(arm, s):
            if side.upper() != 'BOTH':
                raise RuntimeError("Hand {} is not set up. Call setup() first.".format(s))
            continue
        fingers = _hand_controls(arm, s)
        for frame in sorted(set(closed) | set(opened)):
            angle = math.pi / 2 * amount if frame in closed else 0.0
            for f in fingers:
                cb = f.control_bone
                cb.rotation_euler[0] = angle
                cb.keyframe_insert(data_path='rotation_euler', index=0, frame=frame)
        keyed.append(s)
    scene.frame_set(current)
    return {"keyed": keyed, "closed_frames": closed, "open_frames": opened,
            "amount": round(amount, 3)}


def _finger_collides(arm, finger, target, to_world, to_local, depsgraph, tolerance):
    # True when any sampled point along the finger's phalanges (head/mid/tail of each)
    # is inside the target mesh or within tolerance world units of its surface
    for pb in finger.phalanges:
        head, tail = arm.matrix_world @ pb.head, arm.matrix_world @ pb.tail
        for t in (0.0, 0.5, 1.0):
            p = head.lerp(tail, t)
            # closest_point_on_mesh works in object space, so query in target-local
            result, location, normal, _ = target.closest_point_on_mesh(
                to_local @ p, depsgraph=depsgraph)
            if not result:
                continue
            delta = p - to_world @ location
            normal_world = (to_world.to_3x3() @ normal).normalized()
            if delta.dot(normal_world) < 0.0 or delta.length <= tolerance:
                return True
    return False


def find_finger_limits(armature, side='BOTH', target=None, step=5.0, tolerance=0.0):
    """Finds each finger's maximum curl angle before it collides with the target mesh.
    Sweeps all control bones together from 0 to 90 degrees in `step` degree steps and
    tests sampled points along every phalange against the target with
    closest_point_on_mesh(); a finger stops at the last angle that did not collide.
    tolerance: extra contact distance in world units — the test runs on the finger
    bones' centerline, so use roughly the skin/finger half-thickness (0.01-0.03 for
    human-scale hands) to stand in for the flesh. Returns {side: {finger: max_angle_deg}}
    and leaves the hand posed at those limits. A finger already colliding at 0 gets 0."""
    arm = _activate(armature)
    target = _object(target, 'MESH')
    depsgraph = bpy.context.evaluated_depsgraph_get()
    to_local = target.matrix_world.inverted()
    to_world = target.matrix_world

    result = {}
    for s in _sides(side):
        if not _is_setup(arm, s):
            if side.upper() != 'BOTH':
                raise RuntimeError("Hand {} is not set up. Call setup() first.".format(s))
            continue
        fingers = _hand_controls(arm, s)
        limits = {f.name: 90.0 for f in fingers}
        blocked = set()
        angles = [0.0]
        a = step
        while a < 90.0:
            angles.append(a)
            a += step
        angles.append(90.0)
        prev_deg = 0.0
        for deg in angles:
            for f in fingers:
                if f.name in blocked:
                    f.control_bone.rotation_euler[0] = math.radians(limits[f.name])
                else:
                    f.control_bone.rotation_euler[0] = math.radians(deg)
            bpy.context.view_layer.update()
            for f in fingers:
                if f.name not in blocked and _finger_collides(arm, f, target, to_world, to_local, depsgraph, tolerance):
                    limits[f.name] = prev_deg
                    blocked.add(f.name)
            prev_deg = deg
        result[s] = limits
    return result
