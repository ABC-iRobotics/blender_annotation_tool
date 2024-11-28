import os
import json
import bpy
import numbers
from bpy.app.handlers import persistent
from . import utils
import numpy as np

from bpy.types import Context, Event, Scene
from json.decoder import JSONDecodeError

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

        res, message = utils.setup_bat_scene()
        if res == {"CANCELLED"}:
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

        Args:
            context : Current context
        
        Returns:
            status : Execution status
        '''
        res = utils.remove_bat_scene()
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

        Args:
            context : Current context
        
        Returns:
            status : Execution status
        '''

        res, message = utils.bat_render_annotation()
        if res == {"CANCELLED"}:
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

        Args:
            context : Current context
        
        Returns:
            status : Execution status
        '''

        res = utils.export_class_info()
        return res


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


        # Get camera parameters
        intr = [cam.fx,cam.fy,cam.cx,cam.cy]
        distort = [cam.p1,cam.p2,cam.k1,cam.k2,cam.k3,cam.k4]

        # Generate distorion map
        distortion_map = utils.generate_inverse_distortion_map(width, height, intr, distort)
        distortion_map = np.append(distortion_map, np.ones((height,width,1)), axis=2)

        # Save distortion map as image
        if not utils.INV_DISTORTION_MAP_NAME in bpy.data.images:
            dist_map_img = bpy.data.images.new(utils.INV_DISTORTION_MAP_NAME, width, height, alpha=True, float_buffer=True, is_data=True)
        else:
            dist_map_img = bpy.data.images[utils.INV_DISTORTION_MAP_NAME]
        dist_map_img.pixels = distortion_map.flatten()

        # Create a movieclip for using camera lens distortion from compositor
        mov_clip = bpy.data.movieclips.get(utils.BAT_MOVIE_CLIP_NAME)
        if mov_clip is None:
            mov_clip = bpy.data.movieclips.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'clip.png'))
            mov_clip.name = utils.BAT_MOVIE_CLIP_NAME
        mov_clip.tracking.camera.distortion_model = 'BROWN'
        mov_clip.tracking.camera.sensor_width = scene.bat_properties.camera.sensor_width
        fx = scene.bat_properties.camera.fx
        fy = scene.bat_properties.camera.fy if scene.bat_properties.camera.fy > 0 else 0.00001
        mov_clip.tracking.camera.pixel_aspect = max(fx/fy,0.1)
        mov_clip.tracking.camera.focal_length = (fx/scene.render.resolution_x)*scene.bat_properties.camera.sensor_width
        mov_clip.tracking.camera.units = 'MILLIMETERS'
        mov_clip.tracking.camera.principal[0] = scene.bat_properties.camera.cx
        mov_clip.tracking.camera.principal[1] = scene.bat_properties.camera.cy
        mov_clip.tracking.camera.brown_p1 = scene.bat_properties.camera.p1
        mov_clip.tracking.camera.brown_p2 = scene.bat_properties.camera.p2
        mov_clip.tracking.camera.brown_k1 = scene.bat_properties.camera.k1
        mov_clip.tracking.camera.brown_k2 = scene.bat_properties.camera.k2
        mov_clip.tracking.camera.brown_k3 = scene.bat_properties.camera.k3
        mov_clip.tracking.camera.brown_k4 = scene.bat_properties.camera.k4

        # Create new node group for compositor
        bat_distort_group = bpy.data.node_groups.get(utils.BAT_DISTORTION_NODE_GROUP_NAME)
        if bat_distort_group is None:
            bat_distort_group = bpy.data.node_groups.new(utils.BAT_DISTORTION_NODE_GROUP_NAME, 'CompositorNodeTree')

            # Create group inputs
            group_inputs = bat_distort_group.nodes.get('NodeGroupInput')
            if group_inputs is None:
                group_inputs = bat_distort_group.nodes.new('NodeGroupInput')
                bat_distort_group.inputs.new('NodeSocketImage','Image')

            # create group outputs
            group_outputs = bat_distort_group.nodes.get('NodeGroupOutput')
            if group_outputs is None:
                group_outputs = bat_distort_group.nodes.new('NodeGroupOutput')
                bat_distort_group.outputs.new('NodeSocketImage','Image')

            movie_distortion_node = bat_distort_group.nodes.new('CompositorNodeMovieDistortion')
            movie_distortion_node.clip = bpy.data.movieclips[utils.BAT_MOVIE_CLIP_NAME]
            movie_distortion_node.distortion_type = 'DISTORT'

            bat_distort_group.links.new(group_inputs.outputs['Image'], movie_distortion_node.inputs['Image'])
            bat_distort_group.links.new(movie_distortion_node.outputs['Image'], group_outputs.inputs['Image'])


        # Add to compositor if compositor workspace is empty
        if scene.node_tree is None:
            scene.use_nodes = True
            for n in scene.node_tree.nodes:
                scene.node_tree.nodes.remove(n)
            render_layers_node = scene.node_tree.nodes.new('CompositorNodeRLayers')
            render_layers_node.scene = scene
            bat_distortion_node = scene.node_tree.nodes.new('CompositorNodeGroup')
            bat_distortion_node.node_tree = bpy.data.node_groups[utils.BAT_DISTORTION_NODE_GROUP_NAME]
            compositor_node = scene.node_tree.nodes.new('CompositorNodeComposite')

            scene.node_tree.links.new(render_layers_node.outputs['Image'], bat_distortion_node.inputs['Image'])
            scene.node_tree.links.new(bat_distortion_node.outputs['Image'], compositor_node.inputs['Image'])
            

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
        dist_map_img = bpy.data.images.get(utils.INV_DISTORTION_MAP_NAME)
        if not dist_map_img is None:
            w, h = bpy.data.images[utils.INV_DISTORTION_MAP_NAME].size
            dmap = np.array(bpy.data.images[utils.INV_DISTORTION_MAP_NAME].pixels[:], dtype=np.float32)
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
        # Read json file
        filepath = os.path.abspath(scene.bat_properties.camera.calibration_file)
        if os.path.isfile(filepath):
            with open(filepath,'r') as f:
                try:
                    calib_data = json.loads(f.read())
                except JSONDecodeError:
                    self.report({'WARNING'}, 'The selected file is not a valid JSON!')
                    return {'CANCELLED'}
            if isinstance(calib_data, dict):
                if 'cam_mtx' in calib_data:
                    if isinstance(calib_data['cam_mtx'], list):
                        cam_mtx = calib_data['cam_mtx']
                        if len(cam_mtx) == 3 and all((isinstance(e, list) for e in cam_mtx)):
                            if all((len(e)==3 for e in cam_mtx)) and all((all(isinstance(ie,numbers.Number) for ie in e) for e in cam_mtx)):
                                scene.bat_properties.camera.fx = cam_mtx[0][0]
                                scene.bat_properties.camera.fy = cam_mtx[1][1]
                                scene.bat_properties.camera.cx = cam_mtx[0][2]
                                scene.bat_properties.camera.cy = cam_mtx[1][2]
                            else:
                                self.report({'WARNING'}, '"cam_mtx" must be 3x3 matrix!')
                                return {'CANCELLED'}
                        else:
                            self.report({'WARNING'}, '"cam_mtx" must be 3x3 matrix!')
                            return {'CANCELLED'}
                    else:
                        self.report({'WARNING'}, '"cam_mtx" field must be a list!')
                        return {'CANCELLED'}
                if 'dist' in calib_data:
                    if isinstance(calib_data['dist'], list):
                        dist = calib_data['dist']
                        if len(dist) == 6 and all(isinstance(e,numbers.Number) for e in dist):
                            scene.bat_properties.camera.k1 = dist[0]
                            scene.bat_properties.camera.k2 = dist[1]
                            scene.bat_properties.camera.p1 = dist[2]
                            scene.bat_properties.camera.p2 = dist[3]
                            scene.bat_properties.camera.k3 = dist[4]
                            scene.bat_properties.camera.k4 = dist[5]
                        else:
                            self.report({'WARNING'}, '"dist" field must be a list of six numbers! (k1,k2,p1,p2,k3,k4)')
                            return {'CANCELLED'}
                    else:
                        self.report({'WARNING'}, '"dist" field must be a list!')
                        return {'CANCELLED'}
            else:
                self.report({'WARNING'}, 'The file must contain a dictionary!')
                return {'CANCELLED'}
        else:
            self.report({'WARNING'}, 'Could not access the selected file!')
            return {'CANCELLED'}

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