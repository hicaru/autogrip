#----------------------------------------------------------
# File __init__.py
#----------------------------------------------------------
 
#    Addon info
bl_info = {
    "name": "Autogrip",
    "author": "Jetpack Crow",
    "version": (1, 3, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > AutoGrip",
    "description": "Automatically poses hand rigs",
    "category": '3D View'}
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
