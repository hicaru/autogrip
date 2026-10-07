---
name: blender-autogrip
description: Use when a Blender task involves a hand grasping, gripping, holding, wrapping fingers around, or picking up an object (props, tools, cups, weapons). The AutoGrip add-on rigs hand bones to wrap a target mesh; drive it through the Blender MCP's execute-code tool instead of posing finger bones by hand.
---

# AutoGrip: grasping with Blender MCP

AutoGrip adds IK, shrinkwrap "projector" bones and one control bone per finger to a hand rig
(MakeHuman MHX, Rigify, Auto-Rig Pro). Rotating a control bone's local X from 0 to 90 degrees
closes that finger onto the target mesh. Use it whenever hands must hold something.

## Workflow (run inside Blender via the MCP execute-code tool)

1. Check the add-on is enabled. Its module is `autogrip` (legacy install) or
   `bl_ext.user_default.autogrip` (extension install):
   ```python
   import importlib, addon_utils
   name = next((m.__name__ for m in addon_utils.modules() if m.__name__.endswith("autogrip")), None)
   print(name)  # None -> add-on not installed, tell the user to follow README.md Installation
   api = importlib.import_module(name + ".api")
   ```
   If installed but disabled: `addon_utils.enable(name, default_set=True)`.
2. Identify the armature object and the target mesh object (names from `bpy.data.objects`).
3. Grip in one call (sets up if needed, targets the mesh, closes fingers until contact):
   ```python
   print(api.auto_grip("Armature", "Cup", side="R"))   # side: 'L', 'R' or 'BOTH'
   ```
   The result lists each finger's final angle in degrees and whether it touched the target.
4. Verify visually (viewport screenshot via the MCP). Fingers with `touched: False` closed fully
   without reaching the surface: the target is probably out of reach. Move the hand/object with
   the arm's own controls and call `api.grip(...)` again.
   - Any finger with `penetrated_rest: true` was already inside the target before closing:
     the target is badly placed, move it (see "Where to place the target" below) and re-grip.
   - `result[side]["projector_side"]` is `-1` when the projectors (and therefore the bend)
     are on the palm side, `1` on the back of the hand. If the grip closes backwards,
     re-setup with `api.setup(arm, side, rig_type, projector_mirror=True)`.
5. Undo with `api.release("Armature")` (open fingers, keep rig) or `api.reset("Armature")`
   (removes everything AutoGrip added and the finger rotations).

## Where to place the target

Put the target in the CENTER OF THE FIST, not behind the outstretched fingers:

1. `api.quick_pose(arm, side)` to close the hand first.
2. Target center = average of the world positions of the palm/head bones and the
   fingertip bones (the `.03` phalange tails). Example:
   ```python
   import bpy
   from mathutils import Vector
   pts = [b.matrix_world @ pb.head for pb in arm.pose.bones if pb.name.startswith(("palm", "ORG-palm", "thumb.01"))]
   pts += [b.matrix_world @ pb.tail for pb in arm.pose.bones if ".03." in pb.name]
   center = sum(pts, Vector()) / len(pts)
   target.location = center
   ```
3. Then `api.release(arm, side)` and grip on the open hand. A target sitting beyond the
   fingertips (along the extended bones) makes contact detection stop instantly at tiny
   angles or report 90° "not touched" — that is a placement problem, not a rig problem.

## Animating a grip

```python
res = api.grip(arm, 'R')                      # contact grip -> working angles
api.animate_grip(arm, 'R',                    # build the action in one call
                 closed_frames=(13, 37, 61),  # hand closed at these frames
                 open_frames=(1, 25, 49))     # hand open at these frames
api.grip_angles(arm, 'R')                     # read current angles {finger: deg}
api.set_amount(arm, 'R', 0.5)                 # snap all controls to 45 deg, no checks
```
`animate_grip` keyframes `rotation_euler[0]` of every control bone; the drivers move the
phalanges, and everything survives `scene.frame_set()`. For a physical stop instead of a
fixed angle: `api.find_finger_limits(arm, 'R', target, step=5.0, tolerance=0.02)` sweeps
each finger until its bones would hit the target mesh (`tolerance` in world units stands
in for skin thickness) and leaves the hand posed at those limits.

## API (`api` module, all take the armature object or its name)

| Call | Purpose |
|---|---|
| `status(arm)` | rig type (None until setup), per-hand setup state, targets, `control_bones` names |
| `detect_rig_type(arm)` | 'MHX', 'RFY', 'ARP', 'FPS', 'RFY_NO_ORG', or 'GEN' (GEN = generic fallback, always matches) |
| `setup(arm, side='BOTH', rig_type='AUTO', projector_mirror=False)` | build the grip rig; `projector_mirror=True` flips bend direction |
| `set_target(arm, mesh, side='BOTH')` | choose the object to grip |
| `grip(arm, side='BOTH', amount=1.0, contact=True, thumb=True, tolerance=0.35)` | close fingers, stop at contact; reports `penetrated_rest` and `projector_side` |
| `release(arm, side)` / `reset(arm, side, reset_pose=True)` | open / remove rig |
| `quick_pose(arm, side)` | close fully, no contact checks |
| `set_amount(arm, side, amount)` | set all controls at once, 0..1 -> 0..90 deg |
| `grip_angles(arm, side)` | current control angles {finger: deg} |
| `animate_grip(arm, side, closed_frames, open_frames, amount)` | keyframe squeeze/release cycles |
| `find_finger_limits(arm, side, target, step=5.0, tolerance=0.0)` | max non-colliding angle per finger vs target mesh |
| `auto_grip(arm, mesh, side, rig_type='AUTO', **grip_options)` | setup + target + grip |
| `contact_sheet(frames, out, ...)` | render frames into one verification PNG |

## Gotchas

- Never move or pose the finger bones themselves while AutoGrip is set up; use control bones
  (exact names in `api.status(arm)["hands"][side]["control_bones"]`, local X rotation) or the API.
- Setup takes tens of seconds on a real rig. Do not retry while it runs.
- `detect_rig_type` may return `'GEN'` or `'FPS'` — both are valid for setup. `'GEN'` works well
  on unknown/custom rigs (auto-detects finger chains), and `'RFY_NO_ORG'` catches exported/
  game-engine Rigify rigs without `ORG-` bones. Unrecognised naming schemes still land on GEN.
- Target must be a mesh. For several objects, call `set_target` again before each `grip`.
- Control bone local X must stay in [0, 90 deg]; `amount` (0..1) scales this.
- Errors raise `RuntimeError`/`ValueError` with a readable message; report it, don't guess.
