import bpy
from bpy.app.handlers import persistent
from . import utils

from bpy.types import Context

DEFAULT_CLASS_NAME = utils.DEFAULT_CLASS_NAME

# -------------------------------
# Misc. definitions

# Define list of colors for instance segmentation
INSTANCE_COLORS = []
for r in reversed(range(10,240,10)):
    r = r/255
    for g in reversed(range(10,240,10)):
        g = g/255
        for b in reversed(range(10,240,10)):
            b = b/255
            INSTANCE_COLORS.append((r,g,b,1))
    
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
        background_class.mask_color = (0.0,0.0,0.0,1.0)


# -------------------------------
# Operators

# Setup BAT scene
class BAT_OT_setup_bat_scene(bpy.types.Operator):
    """Setup BAT scene"""
    bl_idname = 'bat.setup_bat_scene'
    bl_label = 'Setup BAT scene'
    bl_options = {'REGISTER'}

    def execute(self, context: Context) -> set[str]:
        '''
        Set up a separate scene for BAT

        Args:
            context : Current context
        '''

        active_scene = context.scene
        bat_scene = bpy.data.scenes.get(utils.BAT_SCENE_NAME)

        # Create the BAT scene if it does not exist yet
        if bat_scene is None:
            bat_scene = active_scene.copy()
            bat_scene.name = utils.BAT_SCENE_NAME

        
        utils.add_empty_world(active_scene.world, bat_scene)

        mask_material = utils.make_mask_material(utils.BAT_SEGMENTATION_MASK_MAT_NAME)

        # Use the Cycles render engine
        bat_scene.render.engine = 'CYCLES'
        # Raw view transform so colors will be the same as in BAT
        bat_scene.view_settings.view_transform = 'Raw'
        # Disable anti aliasing and denoising
        bat_scene.cycles.filter_width = 0.01
        bat_scene.cycles.use_denoising = False

        # Image output settings
        utils.apply_output_settings(bat_scene, utils.OutputFormat.PNG)

        
        # Unlink all collections and objects
        for coll in bat_scene.collection.children:
            bat_scene.collection.children.unlink(coll)
        for obj in bat_scene.collection.objects:
            bat_scene.collection.objects.unlink(obj)

        # Add a camera
        cam_copy = active_scene.camera.copy()
        bat_scene.collection.objects.link(cam_copy)
        bat_scene.camera = cam_copy
            

        # Link needed collections/objects to BAT scene
        for classification_class in [c for c in bat_scene.bat_properties.classification_classes if c.name != DEFAULT_CLASS_NAME]:
            # Get original collection and create a new one in the BAT scene for each
            # classification class
            orig_collection = bpy.data.collections.get(classification_class.objects)
            if orig_collection is None:
                # If the collection is deleted or renamed in the meantime
                self.report({'ERROR'},'Could not find collection {}!'.format(classification_class.objects))
                return {'CANCELLED'}
            new_collection = bpy.data.collections.new(classification_class.name)
            bat_scene.collection.children.link(new_collection)

            class_instance_color_gen = utils.instance_color_gen(list(classification_class.mask_color))

            # Duplicate objects
            for obj in orig_collection.objects:
                obj_copy = obj.copy()
                obj_copy.data = obj.data.copy()
                new_collection.objects.link(obj_copy)

                if obj_copy.data.materials:
                    obj_copy.data.materials[0] = mask_material
                else:
                    obj_copy.data.materials.append(mask_material)
            
                if not classification_class.is_instances:
                    color = list(classification_class.mask_color)
                    obj_copy.color = color
                else:
                    try:
                        color = next(class_instance_color_gen)
                        obj_copy.color = color
                        
                    except StopIteration:
                        self.report({'ERROR_INVALID_INPUT'}, 'Too many instances, not enough color codes!')

        return {'FINISHED'}


class BAT_OT_remove_bat_scene(bpy.types.Operator):
    """Remove BAT scene"""
    bl_idname = 'bat.remove_bat_scene'
    bl_label = 'Remove BAT scene'
    bl_options = {'REGISTER'}

    def execute(self, context: Context) -> set[str]:
        '''
        Remove BAT scene

        Args:
            context : Current context
        '''
        bat_scene = bpy.data.scenes.get(utils.BAT_SCENE_NAME)

        if not bat_scene is None:
            # Remove objects, collections, world and material:
            for obj in bat_scene.objects:
                bpy.data.objects.remove(obj)
            for coll in bat_scene.collection.children_recursive:
                bpy.data.collections.remove(coll)
            bpy.data.worlds.remove(bat_scene.world)
            segmentation_mask_material = bpy.data.materials.get(utils.BAT_SEGMENTATION_MASK_MAT_NAME)
            if segmentation_mask_material:
                bpy.data.materials.remove(segmentation_mask_material)
            bpy.data.scenes.remove(bat_scene)
        return {'FINISHED'}


# Render annotations
class BAT_OT_render_annotation(bpy.types.Operator):
    """Render annotation"""
    bl_idname = 'render.bat_render_annotation'
    bl_label = 'Render annotation'
    bl_options = {'REGISTER'}

    def execute(self, context):

        instance_color_gen = instance_color()

        scene = context.scene

        utils.get_annotations(scene)

        return utils.render_segmentation_masks(scene, instance_color_gen, self)


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

classes = [
    BAT_OT_setup_bat_scene, 
    BAT_OT_remove_bat_scene, 
    BAT_OT_render_annotation, 
    BAT_OT_render_animation, 
    BAT_OT_add_class, 
    BAT_OT_remove_class
    ]

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