import bpy
from bpy.app.handlers import persistent
from . import common

DEFAULT_CLASS_NAME = common.DEFAULT_CLASS_NAME

# -------------------------------
# Misc. definitions

# Define list of colors for instance segmentation
INSTANCE_COLORS = []
for val in reversed(range(10,240,10)):
    val = val/255
    INSTANCE_COLORS.append((0,val,val,1))
    INSTANCE_COLORS.append((val,0,val,1))
    INSTANCE_COLORS.append((val,val,0,1))
    
# Create generator for instance segmentation colors
def instance_color():
    for color in INSTANCE_COLORS:
        yield color

# Default value setter for list of classes ('Background' class)
def setDefaultClassName(scene):
    classes = scene.bat_properties.classification_classes
    # set default value if the list of classes is empty
    if not classes:
        background_class = classes.add()
        background_class.name = DEFAULT_CLASS_NAME
        background_class.mask_color = (0,0,0)


# -------------------------------
# Operators

# Render annotations
class BAT_OT_render_annotation(bpy.types.Operator):
    """Render annotation"""
    bl_idname = 'render.bat_render_annotation'
    bl_label = 'Render annotation'
    bl_options = {'REGISTER'}

    def execute(self, context):

        instance_color_gen = instance_color()

        scene = context.scene

        # Save original settings
        original_light = scene.display.shading.light
        original_color_type = scene.display.shading.color_type
        original_anti_aliasing = scene.display.viewport_aa
        original_object_outline = scene.display.shading.show_object_outline
        original_world_background = scene.world.color
        original_view_transform = scene.view_settings.view_transform
        original_filepath = scene.render.filepath
        
        # Setup for rendering the annotations
        scene.display.shading.light = 'FLAT'
        scene.display.shading.color_type = 'OBJECT'
        scene.display.viewport_aa = 'OFF'
        scene.display.shading.show_object_outline = False
        scene.world.color = (0,0,0)
        scene.view_settings.view_transform = 'Raw'
        
        if '.' in scene.render.filepath:
            filepath = scene.render.filepath
        else:
            filepath = scene.render.frame_path(frame=scene.frame_current)
        extension = filepath.split('.')[-1]
        filepath = ''.join(filepath.split('.')[:-1]) + '_annotation'
        
        scene.render.filepath = filepath


        # Set object colors for the masks
        for object in scene.objects:
            object.color = (0,0,0,1)
        
        for classification_class in scene.bat_properties.classification_classes:
            if classification_class.name != DEFAULT_CLASS_NAME and not classification_class.is_instances:
                for obj in bpy.data.collections[classification_class.objects].all_objects:
                    color = list(classification_class.mask_color)
                    color.append(1.0)
                    obj.color = color
            elif classification_class.is_instances:
                try:
                    for obj in bpy.data.collections[classification_class.objects].all_objects:
                        color = next(instance_color_gen)
                        obj.color = color
                    
                except StopIteration:
                    self.report({'ERROR_INVALID_INPUT'}, 'Too many instances, not enough color codes!')
                    return {'FINISHED'}
        

        # Render annotation
        bpy.ops.render.opengl(view_context=False, animation=False, write_still=scene.bat_properties.save_annotation)

        # Reset settings        
        scene.render.filepath = original_filepath
        scene.display.shading.light = original_light
        scene.display.shading.color_type = original_color_type
        scene.display.viewport_aa = original_anti_aliasing
        scene.display.shading.show_object_outline = original_object_outline
        scene.world.color = original_world_background
        scene.view_settings.view_transform = original_view_transform

        return {'FINISHED'}


# Render animation (normal render as well as annotation render)
class BAT_OT_render_animation(bpy.types.Operator):
    """Render animation"""
    bl_idname = 'render.bat_render_animation'
    bl_label = 'Render animation (blocking)'
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        scene = context.scene
        for frame_num in range(scene.frame_start, scene.frame_end+1, scene.frame_step):
            scene.frame_set(frame_num)
            original_render_path = scene.render.filepath
            scene.render.filepath = scene.render.frame_path(frame=scene.frame_current)
            bpy.ops.render.render(write_still=True)
            scene.render.filepath = original_render_path
        return {'FINISHED'}


# Add new class
class BAT_OT_add_class(bpy.types.Operator):
    """Add new class to the list of classes"""
    bl_idname = "bat.add_class"
    bl_label = "Add new class"
    bl_options = {'REGISTER'}
    
    new_class_name: bpy.props.StringProperty(name='name',  default='')


    def execute(self, context):
        
        # If new class name is empty return with error
        if self.new_class_name == '':
            self.report({'ERROR_INVALID_INPUT'}, 'The class name must not be empty!')
            return {'FINISHED'}

        # If new class name already exists return with warning
        if self.new_class_name in [c.name for c in context.scene.bat_properties.classification_classes]:
            self.report({'WARNING'}, 'The class name already exists')
            return {'FINISHED'}

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
    
    def invoke(self, context, event):
        
        self.new_class_name = 'new class'
        
        return context.window_manager.invoke_props_dialog(self, width=200)


# Remove existing class
class BAT_OT_remove_class(bpy.types.Operator):
    """Remove the current class from the list of classes"""
    bl_idname = "bat.remove_class"
    bl_label = "Remove current class"
    bl_options = {'REGISTER'}


    def execute(self, context):
        scene = context.scene
        index = scene.bat_properties.classification_classes.find(scene.bat_properties.current_class)
        
        # Do not allow to delete the default class and to empty the list of classes
        if len(scene.bat_properties.classification_classes) > 0 and scene.bat_properties.current_class != DEFAULT_CLASS_NAME and index >= 1:
            scene.bat_properties.classification_classes.remove(index)
            scene.bat_properties.current_class = scene.bat_properties.classification_classes[index-1].name

        return {'FINISHED'}


# -------------------------------
# Handlers

# Set default value for the list of classes upon registering the addon
def onRegister(scene):
    setDefaultClassName(scene)

# Set default value for the list of classes upon opening Blender, reloading the start-up file via the keys Ctrl N or opening any Blender file
@persistent
def onFileLoaded(scene):
    setDefaultClassName(bpy.context.scene)

# When a render is made and saved in a file automatically render the annotations as well
def onRenderWrite(scene):
    if scene.bat_properties.save_annotation:
        props = bpy.context.window_manager.operator_properties_last('render.opengl')
        props.write_still = True
        override = bpy.context.copy()  # The context has to be overrode because in the handler the context in incomplete
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    override['area'] = area
                    override['window'] = window
                    override['screen'] = window.screen
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            override['region'] = region
                            break
              
        bpy.ops.render.bat_render_annotation(override)


# -------------------------------
# Register/Unregister

classes = [BAT_OT_render_annotation, BAT_OT_render_animation, BAT_OT_add_class, BAT_OT_remove_class]

def register():
    # Add handlers
    bpy.app.handlers.depsgraph_update_pre.append(onRegister)
    bpy.app.handlers.load_post.append(onFileLoaded)
    bpy.app.handlers.render_write.append(onRenderWrite)

    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    # Remove handlers
    if onRegister in bpy.app.handlers.depsgraph_update_pre:
        bpy.app.handlers.depsgraph_update_pre.remove(onRegister)
    if onFileLoaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(onFileLoaded)
    if onRenderWrite in bpy.app.handlers.render_write:
        bpy.app.handlers.render_write.remove(onRenderWrite)
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()