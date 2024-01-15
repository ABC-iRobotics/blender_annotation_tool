import logging
import importlib
 
bl_info = {
    "name": "BAT (Blender Annotation Tool)",
    "description": "3D scene annotation for scene and instance segmentation",
    "author": "Artur Istvan Karoly",
    "blender": (3, 10, 0),
    "version": (1, 0, 0),
    "category": "Render"
}
 
# List of modules making up the addon
module_names = ("properties", "operators", "user_interface")
modules = []

for mod in module_names:
    try:
        modules.append(importlib.import_module('.' + mod, __name__))
    except Exception as e:
        logging.error(e)


def register() -> None:
    '''
    Register operators, properties, and UI elements
    '''
    for mod in modules:
        try:
            mod.register()
        except Exception as e:
            logging.error(e)


def unregister() ->None:
    '''
    Unregister operators, properties, and UI elements
    '''
    for mod in modules:
        try:
            mod.unregister()
        except Exception as e:
            logging.error(e)