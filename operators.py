import os
import json
import bpy
from bpy.app.handlers import persistent
from . import utils
import numpy as np

from bpy.types import Context, Event, Scene

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

        Returns:
            status : Execution status
        '''

        active_scene = context.scene
        bat_scene = bpy.data.scenes.get(utils.BAT_SCENE_NAME)

        # Create the BAT scene if it does not exist yet
        if bat_scene is None:
            bat_scene = active_scene.copy()
            bat_scene.name = utils.BAT_SCENE_NAME

        
        # Add an empty world (no HDRI, no world lighting ...)
        utils.add_empty_world(active_scene.world, bat_scene)


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
        for class_index, classification_class in enumerate([c for c in bat_scene.bat_properties.classification_classes if c.name != utils.DEFAULT_CLASS_NAME]):

            # Create a material for segmentation masks
            mask_material = utils.make_mask_material(utils.BAT_SEGMENTATION_MASK_MAT_NAME+'_'+classification_class.name)
            mask_material.pass_index = class_index+1

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
            for i, obj in enumerate([o for o in orig_collection.objects if hasattr(o.data, 'materials')]):
                # Only add objects to BAT scene that have materials
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


# Remove BAT scene
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
        
        Returns:
            status : Execution status
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
        
        Returns:
            status : Execution status
        '''

        bpy.ops.bat.setup_bat_scene()

        bat_scene = bpy.data.scenes.get(utils.BAT_SCENE_NAME)
        if not bat_scene is None:
            utils.render_scene(bat_scene)

        bpy.ops.bat.remove_bat_scene()

        return {'FINISHED'}


# Export class info
class BAT_OT_export_class_info(bpy.types.Operator):
    """Export class info"""
    bl_idname = 'bat.export_class_info'
    bl_label = 'Export class info'
    bl_options = {'REGISTER'}

    def execute(self, context: Context) -> set[str]:
        '''
        Export information on classes as a JSON in the metadata of the render output

        Args:
            context : Current context
        
        Returns:
            status : Execution status
        '''

        class_info = {}
        class_info['0'] = utils.DEFAULT_CLASS_NAME
        bat_scene = bpy.data.scenes.get(utils.BAT_SCENE_NAME)
        if not bat_scene is None:
            for classification_class in bat_scene.bat_properties.classification_classes:
                mask_material = bpy.data.materials.get(utils.BAT_SEGMENTATION_MASK_MAT_NAME+'_'+classification_class.name)
                if not mask_material is None:
                    class_info[mask_material.pass_index] = classification_class.name
            bat_scene.render.stamp_note_text = json.dumps(class_info)
        return {'FINISHED'}


# Generate distortion map for simulating lens distortions
class BAT_OT_generate_distortion_map(bpy.types.Operator):
    """Generate distortion map"""
    bl_idname = 'bat.generate_distortion_map'
    bl_label = 'Generate distortion map'
    bl_options = {'REGISTER'}

    def execute(self, context: Context) -> set[str]:
        '''
        Generate an image that holds the mapping from distorted pixel coordinates to original (undistorted) pixel coordinates

        Args:
            context : Current context
        
        Returns:
            status : Execution status
        '''

        # Get image parameters
        scene = context.scene
        cam = scene.bat_properties.camera
        width = int(scene.render.resolution_x * (scene.render.resolution_percentage/100))
        height = int(scene.render.resolution_y * (scene.render.resolution_percentage/100))

        upscale_factor = 2  # Used for upscaling to achieve subpixel sampling and to avoid missing values in the map

        # Get camera parameters
        intr = [cam.fx,cam.fy,cam.px,cam.py]
        distort = [cam.p1,cam.p2,cam.k1,cam.k2,cam.k3,cam.k4]

        # Generate distorion map
        distortion_map = utils.generate_inverse_distortion_map(width, height, intr, distort, upscale_factor)
        distortion_map = np.append(distortion_map, np.zeros((height,width,2)), axis=2)

        # Save distortion map as image
        if not 'DistortionMap' in bpy.data.images:
            dist_map_img = bpy.data.images.new('DistortionMap', width, height, alpha=True, float_buffer=True, is_data=True)
        else:
            dist_map_img = bpy.data.images['DistortionMap']
        dist_map_img.pixels = distortion_map.flatten()

        return {'FINISHED'}


# Distort image
class BAT_OT_distort_image(bpy.types.Operator):
    """Distort Image"""
    bl_idname = 'bat.distort_image'
    bl_label = 'Distort Image'
    bl_options = {'REGISTER'}

    def execute(self, context: Context) -> set[str]:
        '''
        Distort Image in the "Viewer Node"

        Args:
            context : Current context
        
        Returns:
            status : Execution status
        '''

        # Read distortion map
        dist_map_img = bpy.data.images.get('DistortionMap')
        if not dist_map_img is None:
            w, h = bpy.data.images['DistortionMap'].size
            dmap = np.array(bpy.data.images['DistortionMap'].pixels[:], dtype=np.float32)
            dmap = np.reshape(dmap, (h, w, 4))[:,:,:]
            ys = dmap[:,:,0].flatten().astype(int)
            xs = dmap[:,:,1].flatten().astype(int)

            # Read image to be distorted
            viewer = bpy.data.images.get('Viewer Node')
            if not viewer is None:
                w, h = viewer.size
                img = np.array(viewer.pixels[:], dtype=np.float32)
                img = np.reshape(img, (h, w, 4))[:,:,:]
                img = img[:,:,0:4]

                # Distort image
                dimg = np.reshape(img[ys,xs],(h,w,4))

                # Save it in an image
                if not 'Distorted Image' in bpy.data.images:
                    dist_img = bpy.data.images.new('Distorted Image', w, h, alpha=True, float_buffer=True, is_data=True)
                else:
                    dist_img = bpy.data.images['Distorted Image']
                dist_img.pixels = dimg.flatten()

        return {'FINISHED'}


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

        Args:
            context : Current context
        
        Returns:
            status : Execution status
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

        Args:
            context : Current context
            event : Event that triggered the invoke method
        
        Returns:
            status : Execution status
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

        Args:
            context : Current context
        
        Returns:
            status : Execution status
        '''
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
def onRegister(scene: Scene) -> None:
    '''
    Setup default class upon registering the addon

    Args:
        scene : Current scene
    '''
    utils.set_default_class_name(scene)

# Set default value for the list of classes upon opening Blender, reloading the start-up file via the keys Ctrl N or opening any Blender file
@persistent
def onFileLoaded(scene: Scene) -> None:
    '''
    Setup default class upon loading a new Blender file

    Args:
        scene : Current scene 
    '''
    utils.set_default_class_name(bpy.context.scene)


# -------------------------------
# Register/Unregister

classes = [
    BAT_OT_setup_bat_scene, 
    BAT_OT_remove_bat_scene, 
    BAT_OT_render_annotation,
    BAT_OT_export_class_info,
    BAT_OT_generate_distortion_map,
    BAT_OT_distort_image,
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