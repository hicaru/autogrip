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
5. Undo with `api.release("Armature")` (open fingers, keep rig) or `api.reset("Armature")`
   (removes everything AutoGrip added and the finger rotations).

## API (`api` module, all take the armature object or its name)

| Call | Purpose |
|---|---|
| `status(arm)` | rig type, which hands are set up, their targets |
| `detect_rig_type(arm)` | 'MHX', 'RFY', 'ARP' or None |
| `setup(arm, side='BOTH', rig_type='AUTO')` | build the grip rig |
| `set_target(arm, mesh, side='BOTH')` | choose the object to grip |
| `grip(arm, side='BOTH', amount=1.0, contact=True, thumb=True, tolerance=0.35)` | close fingers, stop at contact |
| `release(arm, side)` / `reset(arm, side, reset_pose=True)` | open / remove rig |
| `quick_pose(arm, side)` | close fully, no contact checks |
| `auto_grip(arm, mesh, side, rig_type='AUTO', **grip_options)` | setup + target + grip |

## Gotchas

- Never move or pose the finger bones themselves while AutoGrip is set up; use control bones
  (`control_<finger>.<L|R>`, local X rotation) or the API.
- Setup takes tens of seconds on a real rig. Do not retry while it runs.
- Unrecognised rig: `setup` raises. Pass `rig_type` explicitly if the hand bones match one of the
  supported naming schemes, otherwise tell the user the rig isn't supported.
- Target must be a mesh. For several objects, call `set_target` again before each `grip`.
- Control bone local X must stay in [0, 90 deg]; `amount` (0..1) scales this.
- Errors raise `RuntimeError`/`ValueError` with a readable message; report it, don't guess.
