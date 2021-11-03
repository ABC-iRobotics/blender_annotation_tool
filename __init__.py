import sys
 
bl_info = {
    "name": "BAT (Blender Annotation Tool)",
    "description": "3D scene annotation for scene and instance segmentation",
    "author": "Artur Istvan Karoly",
    "blender": (2, 80, 0),
    "version": (0, 0, 1),
    "category": "Render"
}
 
debug = 0 # 0 (ON) or 1 (OFF)
 
# List of modules making up the addon
modules = ("properties", "functionality", "user_interface")

for mod in modules:
    try:
        exec("from . import {mod}".format(mod=mod))
    except Exception as e:
        print(e)
 
def register():
   
    import importlib
    for mod in modules:
        try:
            if debug:
                exec("importlib.reload({mod})".format(mod=mod))
            exec("{mod}.register()".format(mod=mod))
        except Exception as e:
            print(e)
 
def unregister():
 
    for mod in modules:
        try:
            exec("{mod}.unregister()".format(mod=mod))
        except Exception as e:
            print(e)