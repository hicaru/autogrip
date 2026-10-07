#----------------------------------------------------------
# File __init__.py
#----------------------------------------------------------

# Extension metadata lives in blender_manifest.toml; a bl_info dict here would
# make Blender refuse to load the add-on as an extension.
if "bpy" in locals():
    import importlib
    importlib.reload(handrig)
    importlib.reload(api)
    print("Reloaded Autogrip")
else:
    from . import handrig
    from . import api
    print("Imported Autogrip") 


def register():
    handrig.register()

    
def unregister():
    handrig.unregister()

    
if __name__ == "__main__":
    register()
