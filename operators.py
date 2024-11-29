import bpy
from bpy.app.handlers import persistent
from .bat_utils import constants, annotation, camera

from bpy.types import Context, Event, Scene


# ==============================================================================
# SECTION: Annotation Operators
# ==============================================================================
# Description: Operators for BAT Annotation

# Add new class
class BAT_OT_add_class(bpy.types.Operator):
    """Add new class to the list of classes"""
    bl_idname = "bat.add_class"
    bl_label = "Add new class"
    bl_options = {'REGISTER'}
    
    new_class_name: bpy.props.StringProperty(name='name',  default='')


    def execute(self, context: Context) -> set[str]:
        '''
        Add a new class to the list of classes

        Args
            context: Current context
        
        Returns
            Execution status
        '''
        
        # If new class name is empty return with error
        if self.new_class_name == '':
            self.report({'ERROR_INVALID_INPUT'}, 'The class name must not be empty!')
            return {'CANCELLED'}

        # If new class name already exists return with warning
        if self.new_class_name in [c.name for c in context.scene.bat_properties.classification_classes]:
            self.report({'WARNING'}, 'The class name already exists')
            return {'CANCELLED'}

        # Add new class
        new_class = context.scene.bat_properties.classification_classes.add()
        new_class.name = self.new_class_name
        
        # Update currently selected class
        context.scene.bat_properties.current_class = context.scene.bat_properties.classification_classes[-1].name
        
        # Redraw UI so the UI panel is updated
        for region in context.area.regions:
            if region.type == "UI":
                region.tag_redraw()

        return {'FINISHED'}
    
    def invoke(self, context: Context, event: Event) -> set[str]:
        '''
        Display "Add new class dialog box"

        Args
            context: Current context
            event: Event that triggered the invoke method
        
        Returns
            Execution status
        '''
        
        self.new_class_name = 'new class'
        
        return context.window_manager.invoke_props_dialog(self, width=200)


# Remove existing class
class BAT_OT_remove_class(bpy.types.Operator):
    """Remove the current class from the list of classes"""
    bl_idname = "bat.remove_class"
    bl_label = "Remove current class"
    bl_options = {'REGISTER'}

    def execute(self, context: Context) -> set[str]:
        '''
        Remove the current class from the list of classes

        Args
            context: Current context
        
        Returns
            Execution status
        '''
        scene = context.scene
        index = scene.bat_properties.classification_classes.find(scene.bat_properties.current_class)
        
        # Do not allow to delete the default class and to empty the list of classes
        if len(scene.bat_properties.classification_classes) > 0 and scene.bat_properties.current_class != constants.DEFAULT_CLASS_NAME and index >= 1:
            scene.bat_properties.classification_classes.remove(index)
            scene.bat_properties.current_class = scene.bat_properties.classification_classes[index-1].name

        return {'FINISHED'}

# Setup BAT scene
class BAT_OT_setup_bat_scene(bpy.types.Operator):
    """Setup BAT scene"""
    bl_idname = 'bat.setup_bat_scene'
    bl_label = 'Setup BAT scene'
    bl_options = {'REGISTER'}

    def execute(self, context: Context) -> set[str]:
        '''
        Set up a separate scene for BAT

        Args
            context: Current context

        Returns
            Execution status
        '''

        res, message = annotation.setup_bat_scene()
        if res == {'CANCELLED'}:
            self.report({'ERROR'}, message)
        return res


# Remove BAT scene
class BAT_OT_remove_bat_scene(bpy.types.Operator):
    """Remove BAT scene"""
    bl_idname = 'bat.remove_bat_scene'
    bl_label = 'Remove BAT scene'
    bl_options = {'REGISTER'}

    def execute(self, context: Context) -> set[str]:
        '''
        Remove BAT scene

        Args
            context: Current context
        
        Returns
            Execution status
        '''
        res = annotation.remove_bat_scene()
        return res


# Render annotations
class BAT_OT_render_annotation(bpy.types.Operator):
    """Render annotation"""
    bl_idname = 'render.bat_render_annotation'
    bl_label = 'Render annotation'
    bl_options = {'REGISTER'}

    def execute(self, context: Context) -> set[str]:
        '''
        Render annotations

        Args
            context: Current context
        
        Returns
            Execution status
        '''

        res, message = annotation.bat_render_annotation()
        if res == {'CANCELLED'}:
            self.report({'ERROR'}, message)
        return res


# Export class info
class BAT_OT_export_class_info(bpy.types.Operator):
    """Export class info"""
    bl_idname = 'bat.export_class_info'
    bl_label = 'Export class info'
    bl_options = {'REGISTER'}

    def execute(self, context: Context) -> set[str]:
        '''
        Export information on classes as a JSON in the metadata of the render output

        Args
            context: Current context
        
        Returns
            Execution status
        '''

        res = annotation.export_class_info()
        return res



# ==============================================================================
# SECTION: Camera Operators
# ==============================================================================
# Description: Operators for BAT Camera


# Generate distortion map for simulating lens distortions
class BAT_OT_generate_distortion_map(bpy.types.Operator):
    """Generate distortion map"""
    bl_idname = 'bat.generate_distortion_map'
    bl_label = 'Generate distortion map'
    bl_options = {'REGISTER'}

    def execute(self, context: Context) -> set[str]:
        '''
        Generate an image that holds the mapping from distorted pixel coordinates to original (undistorted) pixel coordinates

        Args
            context: Current context
        
        Returns
            Execution status
        '''

        # Get image parameters
        scene = context.scene
        return camera.setup_bat_distortion(scene)


# Distort image
class BAT_OT_distort_image(bpy.types.Operator):
    """Distort Image"""
    bl_idname = 'bat.distort_image'
    bl_label = 'Distort Image'
    bl_options = {'REGISTER'}

    def execute(self, context: Context) -> set[str]:
        '''
        Distort Image in the "Viewer Node"

        Args
            context: Current context
        
        Returns
            Execution status
        '''

        res,message = camera.distort_image('Viewer Node')
        if res == {'CANCELLED'}:
            self.report({'WARNING'}, message)
        return res


# Import camera data
class BAT_OT_import_camera_data(bpy.types.Operator):
    """Import camera data"""
    bl_idname = 'bat.import_camera_data'
    bl_label = 'Import camera data'
    bl_options = {'REGISTER'}

    def execute(self, context: Context) -> set[str]:
        '''
        Import camera data from json file

        Args:
            context : Current context
        
        Returns:
            status : Execution status
        '''

        scene = context.scene
        res, message = camera.import_camera_data(scene)
        if res == {'CANCELLED'}:
            self.report({'WARNING'}, message)
        return res



# ==============================================================================
# SECTION: Handlers
# ==============================================================================
# Description: Functions to handle events

# Set default value for the list of classes upon registering the addon
def onRegister(scene: Scene) -> None:
    '''
    Setup default class upon registering the addon

    Args:
        scene : Current scene
    '''
    annotation.set_default_class_name(scene)

# Set default value for the list of classes upon opening Blender, reloading the start-up file via the keys Ctrl N or opening any Blender file
@persistent
def onFileLoaded(scene: Scene) -> None:
    '''
    Setup default class upon loading a new Blender file

    Args:
        scene : Current scene 
    '''
    annotation.set_default_class_name(bpy.context.scene)



# ==============================================================================
# SECTION: Register/Unregister
# ==============================================================================
# Description: Make defined classes available in Blender

classes = [
    BAT_OT_setup_bat_scene, 
    BAT_OT_remove_bat_scene, 
    BAT_OT_render_annotation,
    BAT_OT_export_class_info,
    BAT_OT_generate_distortion_map,
    BAT_OT_distort_image,
    BAT_OT_import_camera_data,
    BAT_OT_add_class, 
    BAT_OT_remove_class
    ]

def register() -> None:
    '''
    Register operators and handlers
    '''
    bpy.app.handlers.depsgraph_update_pre.append(onRegister)
    bpy.app.handlers.load_post.append(onFileLoaded)

    for cls in classes:
        bpy.utils.register_class(cls)

def unregister() -> None:
    '''
    Unregister operators and handlers
    '''
    if onRegister in bpy.app.handlers.depsgraph_update_pre:
        bpy.app.handlers.depsgraph_update_pre.remove(onRegister)
    if onFileLoaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(onFileLoaded)
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()