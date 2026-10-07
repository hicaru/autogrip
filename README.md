# Autogrip

This is a helpful little tool for hand rigs that lets them automatically grab onto mesh props. So far the types of rig it works on are MakeHuman Exchange, Rigify, and Auto-Rig Pro, but I'm taking requests for other common rig types and I'm working on adding a "custom" option. 

# Installation

Requires Blender 5.2 or newer.

1. Download this repository as a ZIP (GitHub: **Code > Download ZIP**, or a release ZIP). Don't unzip it.
2. In Blender: **Edit > Preferences > Get Extensions**, open the dropdown arrow (top right) and choose **Install from Disk...**, then pick the ZIP.
3. Make sure **AutoGrip** is enabled in the list.
4. In the 3D viewport press **N**, and you'll find an **AutoGrip** tab in the sidebar (object mode, with an armature active).

Developing from a git checkout: name the folder `autogrip` and symlink it into your user extensions folder (`<Blender config>/extensions/user_default/autogrip`), or run `blender --command extension build` inside it to produce an installable ZIP.

# Using it with an AI agent (Blender MCP)

AutoGrip has a scripting API (`api.py`) so an agent connected to Blender through an MCP server can grip things without clicking. The agent finds out about it from a skill:

1. Copy `skills/blender-autogrip` into your agent's skills folder (for Claude Code: `~/.claude/skills/` or `<project>/.claude/skills/`). `AGENTS.md` carries the short version for other agents.
2. Connect your Blender MCP server (it must offer an execute-Python tool) and ask for something like "make the right hand hold the cup".
3. The agent runs, inside Blender:

```python
import importlib
api = importlib.import_module("bl_ext.user_default.autogrip.api")   # "autogrip.api" for a legacy add-on install
api.auto_grip("Armature", "Cup", side="R")
```

Main calls: `setup`, `set_target`, `grip` (stops each finger at contact with the target), `release`, `reset`, `status`, `quick_pose`, `auto_grip`. See the docstrings in `api.py` or `skills/blender-autogrip/SKILL.md`.

# Tutorial

With the armature you want to use selected, you can pick which type of rig it is from the drop-down. Formats supported so far are MakeHuman Exchange, Rigify, and Auto-Rig Pro. 

If it's not a model you made and you're not 100% sure, you can use "Guess Rig Type" to quickly compare its hand setup to the ones this program can handle.

Click "setup" to assemble both hands, or just "Setup Right" or "Setup Left" if you don't need both (or your model doesn't have both).

It'll take about 20-30 seconds, during which a lot of my debug notes will print in the system console. Let that finish, and you'll have a tangle of small needley bones sticking off the hands, but the pose won't change yet. 
(The control bones are put in a bone collection called "AutoGrip Controls". The needley projector bones are in "AutoGrip Projectors", which is hidden; turn it on in the Armature properties if you want to see them.)

The influence of the contraints depends on the rotation of the control bones - those are the longer ones that stick out from the knuckles. If they're at rest, pointing out from the back of the hand, it's 0%. If they're rotated 90 degrees on their local X axis, so they jab forward over the fingers like Wolverine claws, it's 100%.

"Quick Pose" puts all of those to 90 degrees, and takes a guess at where the opposable thumbs should be positioned. The hands should now be fists, but the thumb positions often need a bit of manual (hah) tweaking in pose mode.

If you select another mesh object, then select the armature again so armature is active, you'll have options for "Grip Target R" and "Grip Target L." These actually set the targets of the constraints to that other mesh you have selected, so the hand can grab on properly. You can also set a different target later without having to run the initial setup again.

I'm going to add more options to fine-tune the "collision" results, but most of the time, the control bones will have all you need. Scaling them affects the offset of the shrinkwrap constraints and can help with a bit of clipping.

If you're sick of it and you want your old armature back, "Reset Hand R" and "Reset Hand L" clean up after themselves pretty well, deleting everything this script did and leaving the original rig untouched.


https://user-images.githubusercontent.com/84341068/208527863-93669d1c-66f0-4e3d-a5e2-78c5ff099de9.mp4

https://user-images.githubusercontent.com/84341068/208528078-01ded0e2-a567-4b24-b028-415d16b8c830.mp4
