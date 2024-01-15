import bpy
from bpy.app.handlers import persistent
from . import utils

from bpy.types import Context

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

        
        # Add an empty world (no HDRI, no world lighting)
        utils.add_empty_world(active_scene.world, bat_scene)

        # Create a material for segmentation masks
        mask_material = utils.make_mask_material(utils.BAT_SEGMENTATION_MASK_MAT_NAME)

        # Render settings
        utils.apply_render_settings(bat_scene)

        # Image output settings (we use OpenEXR Multilayer)
        utils.apply_output_settings(bat_scene, utils.OutputFormat.OPEN_EXR)


        # Unlink all collections and objects from BAT scene
        for coll in bat_scene.collection.children:
            bat_scene.collection.children.unlink(coll)
        for obj in bat_scene.collection.objects:
            bat_scene.collection.objects.unlink(obj)
            

        # Link needed collections/objects to BAT scene
        for classification_class in [c for c in bat_scene.bat_properties.classification_classes if c.name != utils.DEFAULT_CLASS_NAME]:
            # Get original collection and create a new one in the BAT scene for each
            # classification class
            orig_collection = bpy.data.collections.get(classification_class.objects)
            if orig_collection is None:
                # If the collection is deleted or renamed in the meantime
                self.report({'ERROR'},'Could not find collection {}!'.format(classification_class.objects))
                return {'CANCELLED'}
            new_collection = bpy.data.collections.new(classification_class.name)
            bat_scene.collection.children.link(new_collection)

            # Duplicate objects
            for i, obj in enumerate(orig_collection.objects):
                obj_copy = obj.copy()
                obj_copy.data = obj.data.copy()
                obj_copy.pass_index = 100  # Pass index controls emission strength in the mask material (>100 for visualization)
                new_collection.objects.link(obj_copy)

                # Assign segmentation mask material
                if obj_copy.data.materials:
                    obj_copy.data.materials[0] = mask_material
                else:
                    obj_copy.data.materials.append(mask_material)
            
                # Set object color
                color = list(classification_class.mask_color)
                obj_copy.color = color

                # For instances increase emission strength in the material so they can be distinguished
                if classification_class.is_instances:
                    obj_copy.pass_index += i

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

    def execute(self, context: Context) -> set[str]:
        '''
        Render annotations

        Args:
            context : Current context
        '''

        bpy.ops.bat.setup_bat_scene()

        bat_scene = bpy.data.scenes.get(utils.BAT_SCENE_NAME)
        if not bat_scene is None:
            utils.render_scene(bat_scene)

        # utils.get_annotations(active_scene)
        # utils.render_segmentation_masks(active_scene, instance_color_gen, self)

        bpy.ops.bat.remove_bat_scene()

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
        if len(scene.bat_properties.classification_classes) > 0 and scene.bat_properties.current_class != utils.DEFAULT_CLASS_NAME and index >= 1:
            scene.bat_properties.classification_classes.remove(index)
            scene.bat_properties.current_class = scene.bat_properties.classification_classes[index-1].name

        return {'FINISHED'}


# -------------------------------
# Handlers

# Set default value for the list of classes upon registering the addon
def onRegister(scene):
    utils.set_default_class_name(scene)

# Set default value for the list of classes upon opening Blender, reloading the start-up file via the keys Ctrl N or opening any Blender file
@persistent
def onFileLoaded(scene):
    utils.set_default_class_name(bpy.context.scene)

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