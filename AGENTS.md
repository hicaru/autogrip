# AGENTS.md

AutoGrip is a Blender 5.2 add-on that rigs hand bones to grip a target mesh.

## For agents driving Blender (MCP)

If a task has a hand grasping, holding, gripping or picking up an object, use AutoGrip
instead of posing finger bones manually. Full instructions: `skills/blender-autogrip/SKILL.md`.
Short version, run through the Blender MCP's execute-code tool:

```python
import importlib
api = importlib.import_module("autogrip.api")   # "bl_ext.user_default.autogrip.api" when installed as an extension
api.auto_grip("ArmatureName", "TargetMeshName", side="R")   # 'L', 'R' or 'BOTH'
api.release("ArmatureName")   # open fingers
api.reset("ArmatureName")     # remove everything AutoGrip added
```

## For code changes

- `handrig.py`: rig building, operators, panel. `api.py`: selection-independent scripting API;
  operators are thin wrappers over it.
- Headless check: from the parent folder of this repo (folder must be named `autogrip`):
  `blender -b --factory-startup --python autogrip/tests/smoke.py` (prints `SMOKE OK`).
- Everything the add-on creates is prefixed `AutoGrip_`/`projector_`/`control_` so reset can find it.
