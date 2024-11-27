import os
import bpy
import json
import numpy as np
from enum import Enum
from bpy.types import Object, Collection, Material, World, Scene


# -------------------------------
# Constants

DEFAULT_CLASS_NAME = 'Background'
BAT_SCENE_NAME = 'BAT_Scene'
BAT_VIEW_LAYER_NAME = 'BAT_ViewLayer'
BAT_SEGMENTATION_MASK_MAT_NAME = 'BAT_segmentation_mask'
INV_DISTORTION_MAP_NAME = 'DistortionMap'
BAT_MOVIE_CLIP_NAME = 'BAT_MovieClip'
BAT_DISTORTION_NODE_GROUP_NAME = 'BAT_Distort'


# -------------------------------
# Enums

class OutputFormat(str, Enum):
    '''
    String Enum to store image output formats

    Keys:
        PNG : PNG file format
        OPEN_EXR : OpenEXR Multilayer format
    '''
    PNG = 'PNG'
    OPEN_EXR = 'OPEN_EXR_MULTILAYER'

class ColorDepth(str, Enum):
    '''
    String Enum to store output color depth

    Keys:
        HALF : Half float (16 bits)
        FULL : Full float (32 bits)
    '''
    HALF = '16'
    FULL = '32'


# -------------------------------
# Functions

def set_default_class_name(scene: Scene) -> None:
    '''
    Set the default class name for list of classes ('Background' class)

    Args:
        scene : Scene in which the change will be applied
    '''
    classes = scene.bat_properties.classification_classes
    # set default value if the list of classes is empty
    if not classes:
        background_class = classes.add()
        background_class.name = DEFAULT_CLASS_NAME
        background_class.mask_color = (0.0,0.0,0.0,1.0)


def find_parent_collection(root_collection: Collection, collection: Collection) -> Collection | None:
    '''
    Recursive function to find and return parent collection of given collection

    Args:
        root_collection : Root collection to start the search from
        collection : Collection to look for

    Returns:
        parent : Parent of "collection" if "collection" exists in the tree, else None
    '''
    if collection.name in root_collection.children:
        return root_collection
    else:
        for child_collection in root_collection.children:
            parent = find_parent_collection(child_collection, collection)
            if parent:
                return parent


def find_root(obj: Object) -> Object:
    '''
    Recursive function for finding the root object of nested (parented objects)

    Args:
        obj: The object for which the root parent is sought

    Returns:
        root: The root object
    '''
    if obj.parent is None:
        return obj
    else:
        return find_root(obj.parent)


def setup_compositor(scene: Scene) -> None:
    '''
    Set up the compositor workspace of the scene

    Args:
        scene: Scene where the compositor will be set
    '''
    scene.use_nodes = True

    # Delete all nodes from compositor
    for n in scene.node_tree.nodes:
        scene.node_tree.nodes.remove(n)
    
    # Add nodes
    render_layers_node = scene.node_tree.nodes.new('CompositorNodeRLayers')
    render_layers_node.name = 'RLayersBAT'
    render_layers_node.scene = scene
    render_layers_node.layer = BAT_VIEW_LAYER_NAME

    compositor_node = scene.node_tree.nodes.new('CompositorNodeComposite')

    inv_distortion_map = bpy.data.images.get(INV_DISTORTION_MAP_NAME)
    image_node = None
    flip_node = None
    if not inv_distortion_map is None:
        image_node = scene.node_tree.nodes.new('CompositorNodeImage')
        image_node.image = inv_distortion_map
        flip_node = scene.node_tree.nodes.new('CompositorNodeFlip')
        flip_node.axis = 'Y'

    separate_rgba_node = None
    combine_rgba_node = None
    math_node_1 = None
    math_node_2 = None
    if scene.bat_properties.optical_flow_generation:
        separate_rgba_node = scene.node_tree.nodes.new('CompositorNodeSepRGBA')
        combine_rgba_node = scene.node_tree.nodes.new('CompositorNodeCombRGBA')
        math_node_1 = scene.node_tree.nodes.new('CompositorNodeMath')
        math_node_1.operation = 'MULTIPLY'
        math_node_1.inputs[1].default_value = -1
        math_node_2 = scene.node_tree.nodes.new('CompositorNodeMath')
        math_node_2.operation = 'MULTIPLY'
        math_node_2.inputs[1].default_value = -1

    viewer_node = scene.node_tree.nodes.new('CompositorNodeViewer')

    file_output_node = scene.node_tree.nodes.new('CompositorNodeOutputFile')
    file_output_node.format.file_format = OutputFormat.OPEN_EXR
    file_output_node.format.color_mode = 'RGBA'
    file_output_node.format.color_depth = ColorDepth.FULL
    file_output_node.base_path = scene.render.filepath

    # Create links
    scene.node_tree.links.new(render_layers_node.outputs['Image'], viewer_node.inputs['Image'])
    scene.node_tree.links.new(render_layers_node.outputs['Image'], compositor_node.inputs['Image'])
    scene.node_tree.links.new(render_layers_node.outputs['Image'], file_output_node.inputs['Image'])

    file_output_node.file_slots.new('ClassID')
    scene.node_tree.links.new(render_layers_node.outputs['IndexMA'], file_output_node.inputs['ClassID'])

    file_output_node.file_slots.new('InstanceID')
    scene.node_tree.links.new(render_layers_node.outputs['IndexOB'], file_output_node.inputs['InstanceID'])

    if scene.bat_properties.depth_map_generation:
        file_output_node.file_slots.new('Depth')
        scene.node_tree.links.new(render_layers_node.outputs['Depth'], file_output_node.inputs['Depth'])

    if scene.bat_properties.surface_normal_generation:
        file_output_node.file_slots.new('Normal')
        scene.node_tree.links.new(render_layers_node.outputs['Normal'], file_output_node.inputs['Normal'])

    if scene.bat_properties.optical_flow_generation and not separate_rgba_node is None and not combine_rgba_node is None and not math_node_1 is None and not math_node_2 is None:
        file_output_node.file_slots.new('Flow')
        scene.node_tree.links.new(render_layers_node.outputs['Vector'], separate_rgba_node.inputs['Image'])
        # X component of backward flow goes in B
        scene.node_tree.links.new(separate_rgba_node.outputs['R'], combine_rgba_node.inputs['B'])
        # Y component of backward flow needs to be flipped (because in blender Y=0 is at the bottom of the image)
        scene.node_tree.links.new(separate_rgba_node.outputs['G'], math_node_1.inputs[0])
        # Y component of backward flow goes in A
        scene.node_tree.links.new(math_node_1.outputs[0], combine_rgba_node.inputs['A'])
        # X component of forward flow is computed by inverting backward flow for next frame
        scene.node_tree.links.new(separate_rgba_node.outputs['B'], math_node_2.inputs[0])
        # X component of forward flow goes in G to be compatible with DistortionMap
        scene.node_tree.links.new(math_node_2.outputs[0], combine_rgba_node.inputs['G'])
        # Y component of forward flow goes in R to be compatible with DistortionMap (this doesn't need to be inverted, because it should be inverted twice:
        # once because we compute it from the backwards flow from the next frame, and then again for taking Blender's Y=0 being at the bottom into account)
        scene.node_tree.links.new(separate_rgba_node.outputs['A'], combine_rgba_node.inputs['R'])
        scene.node_tree.links.new(combine_rgba_node.outputs['Image'], file_output_node.inputs['Flow'])

    if not image_node is None and not flip_node is None:
        file_output_node.file_slots.new(INV_DISTORTION_MAP_NAME)
        scene.node_tree.links.new(image_node.outputs['Image'], flip_node.inputs['Image'])
        scene.node_tree.links.new(flip_node.outputs['Image'], file_output_node.inputs[INV_DISTORTION_MAP_NAME])


def add_empty_world(world: World, scene: Scene) -> None:
    '''
    Create an "empty" (dark) copy of the given world and link it to a scene

    Args:
        world : Input world to copy settings from
        scene : Scene to which the empty world will be linked
    '''
    # Create a copy of the world
    world_copy = world.copy()
    scene.world = world_copy

    # Set up node tree
    scene.world.use_nodes = True
    for n in scene.world.node_tree.nodes:
        scene.world.node_tree.nodes.remove(n)
    # Only add an output node (the world will be dark)
    world_output_node = scene.world.node_tree.nodes.new('ShaderNodeOutputWorld')
    world_output_node.is_active_output = True
    
    return world_copy


def make_mask_material(material_name: str) -> Material:
    '''
    Create material for making segmentation masks

    Args:
        material_name : The name of the new material

    Returns:
        material : The created material
    '''
    # Create new material
    mask_material = bpy.data.materials.new(material_name)
    mask_material.use_nodes = True
    for n in mask_material.node_tree.nodes:
        mask_material.node_tree.nodes.remove(n)

    # Add nodes (Object Info, Emission shader and Material output)
    obj_info_node = mask_material.node_tree.nodes.new('ShaderNodeObjectInfo')
    emission_shader_node = mask_material.node_tree.nodes.new('ShaderNodeEmission')
    matrial_output_node = mask_material.node_tree.nodes.new('ShaderNodeOutputMaterial')
    matrial_output_node.is_active_output = True

    # Create links
    # Emission color will be object color (object color is set to BAT mask color during scene setup)
    mask_material.node_tree.links.new(emission_shader_node.inputs['Color'], obj_info_node.outputs['Color'])
    # Emission strength will be object index (to enable instance segmentation)
    mask_material.node_tree.links.new(emission_shader_node.inputs['Strength'], obj_info_node.outputs['Object Index'])
    mask_material.node_tree.links.new(matrial_output_node.inputs['Surface'], emission_shader_node.outputs['Emission'])

    return mask_material


def apply_render_settings(scene: Scene) -> None:
    '''
    Apply render settings for scene for segmentation mask rendering

    Args:
        scene : Scene to apply the render settings to
    '''

    # Create a new ViewLayer for BAT
    bat_view_layer = scene.view_layers.new(BAT_VIEW_LAYER_NAME)
    for view_layer in scene.view_layers:
        if view_layer != bat_view_layer:
            scene.view_layers.remove(view_layer)

    # Use the Cycles render engine
    scene.render.engine = 'CYCLES'

    # Use transparent background, so alpha channel can be used for binary segmentation
    scene.render.film_transparent = True

    # Reduce samples to 1 to speed up rendering and avoid color mixing
    scene.cycles.samples = 1

    # Add note to render output metadata
    scene.render.use_stamp_note = True

    # Disable anti aliasing and denoising (preserve sharpe edges of masks)
    scene.cycles.filter_width = 0.01
    scene.cycles.use_denoising = False

    # Set max bounces for light paths (only diffuse is needed)
    # We use emission, so light hitting the camera directly is important
    scene.cycles.max_bounces = 1
    scene.cycles.diffuse_bounces = 1
    scene.cycles.glossy_bounces = 0
    scene.cycles.transmission_bounces = 0
    scene.cycles.volume_bounces = 0
    scene.cycles.transparent_max_bounces = 0

    # Raw view transform so colors will be the same as set in BAT
    scene.view_settings.view_transform = 'Raw'

    # Setup data passes
    bat_view_layer.use_pass_object_index = True  # Instance ID
    bat_view_layer.use_pass_material_index = True  # Class ID
    if scene.bat_properties.depth_map_generation:
        bat_view_layer.use_pass_z = True
    if scene.bat_properties.surface_normal_generation:
        bat_view_layer.use_pass_normal = True
    if scene.bat_properties.optical_flow_generation:
        bat_view_layer.use_pass_vector = True


def apply_output_settings(scene: Scene, output_format: OutputFormat=OutputFormat.PNG) -> None:
    '''
    Apply output settings for scene

    Args:
        scene : Scene to apply the output settings to
        output_format : Output file format
    '''
    # Set output file format
    scene.render.image_settings.file_format = output_format
    scene.render.image_settings.color_mode = 'RGBA'
    match output_format:
        case OutputFormat.PNG:
            scene.render.image_settings.color_depth = ColorDepth.HALF
            scene.render.image_settings.compression = 0
        case OutputFormat.OPEN_EXR:
            scene.render.image_settings.color_depth = ColorDepth.FULL

    # Set output file path
    if '.' in scene.render.filepath:
        filepath = os.path.dirname(scene.render.filepath)
    else:
        filepath = scene.render.filepath
    filepath += '/annotations/'
    
    scene.render.filepath = filepath


def export_class_info() -> set[str]:
    '''Set the "Note" metadata for the render output
    '''
    class_info = {}
    class_info['0'] = DEFAULT_CLASS_NAME
    bat_scene = bpy.data.scenes.get(BAT_SCENE_NAME)
    if not bat_scene is None:
        for classification_class in bat_scene.bat_properties.classification_classes:
            mask_material = bpy.data.materials.get(BAT_SEGMENTATION_MASK_MAT_NAME+'_'+classification_class.name)
            if not mask_material is None:
                class_info[mask_material.pass_index] = classification_class.name
        bat_scene.render.stamp_note_text = json.dumps(class_info)
    return {'FINISHED'}


def setup_bat_scene() -> tuple[set[str],str]:
    '''Set up a separate scene for BAT
    '''
    active_scene = bpy.context.scene
    bat_scene = bpy.data.scenes.get(BAT_SCENE_NAME)

    # Create the BAT scene if it does not exist yet
    if bat_scene is None:
        bat_scene = active_scene.copy()
        bat_scene.name = BAT_SCENE_NAME

    
    # Add an empty world (no HDRI, no world lighting ...)
    add_empty_world(active_scene.world, bat_scene)


    # Render settings
    apply_render_settings(bat_scene)

    # Image output settings (we use OpenEXR Multilayer)
    apply_output_settings(bat_scene, OutputFormat.OPEN_EXR)


    # Unlink all collections and objects from BAT scene
    for coll in bat_scene.collection.children:
        bat_scene.collection.children.unlink(coll)
    for obj in bat_scene.collection.objects:
        bat_scene.collection.objects.unlink(obj)
        

    # Link needed collections/objects to BAT scene
    for class_index, classification_class in enumerate([c for c in bat_scene.bat_properties.classification_classes if c.name != DEFAULT_CLASS_NAME]):

        # Create a material for segmentation masks
        mask_material = make_mask_material(BAT_SEGMENTATION_MASK_MAT_NAME+'_'+classification_class.name)
        mask_material.pass_index = class_index+1

        # Get original collection and create a new one in the BAT scene for each
        # classification class
        orig_collection = bpy.data.collections.get(classification_class.objects)
        if orig_collection is None:
            # If the collection is deleted or renamed in the meantime
            return ({'CANCELLED'}, f'Could not find collection {classification_class.objects}!')
        new_collection = bpy.data.collections.new(classification_class.name)
        bat_scene.collection.children.link(new_collection)

        # Duplicate objects
        orig_coll_objects = [o for o in orig_collection.objects if hasattr(o, 'parent')]
        root_objects = list({find_root(o) for o in orig_coll_objects})

        for i, obj in enumerate(root_objects):
            all_object = obj.children_recursive
            all_object.insert(0, obj)
            for part in all_object:
                # Only add objects to BAT scene that have materials
                if part.name in orig_collection.objects and hasattr(part.data, 'materials'):
                    obj_copy = part.copy()
                    obj_copy.data = part.data.copy()
                    obj_copy.pass_index = 100  # Pass index controls emission strength in the mask material (>100 for visualization)
                    new_collection.objects.link(obj_copy)

                    # Remove all materials from the object
                    obj_copy.data.materials.clear()

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

    # Export class info
    res = export_class_info()

    # Setup compositor workspace
    setup_compositor(bat_scene)

    return (res, '')


def remove_bat_scene() -> set[str]:
    '''Remove BAT Scene
    '''
    bat_scene = bpy.data.scenes.get(BAT_SCENE_NAME)

    if not bat_scene is None:
        # Remove objects, collections, world and material:
        for obj in bat_scene.objects:
            bpy.data.objects.remove(obj)
        for coll in bat_scene.collection.children_recursive:
            bpy.data.collections.remove(coll)
        bpy.data.worlds.remove(bat_scene.world)
        segmentation_mask_material = bpy.data.materials.get(BAT_SEGMENTATION_MASK_MAT_NAME)
        if segmentation_mask_material:
            bpy.data.materials.remove(segmentation_mask_material)
        bpy.data.scenes.remove(bat_scene)

    return {'FINISHED'}


def render_scene(scene: Scene|None, write_still: bool=False) -> None:
    '''
    Render scene

    Args:
        scene : Scene to render
        write_still: Save render result
    '''
    if scene is None:
        scene = bpy.context.scene

    # Set file name
    render_filepath_temp = scene.render.filepath
    scene.render.filepath = scene.render.frame_path(frame=scene.frame_current)
        
    # Render image
    bpy.ops.render.render(write_still=write_still, scene=scene.name)

    # Reset output path
    scene.render.filepath = render_filepath_temp


def bat_render_annotation() -> tuple[set[str], str]:
    '''Render annotations with BAT
    '''
    res, message = setup_bat_scene()
    if res == {"CANCELLED"}:
        return (res, message)

    bat_scene = bpy.data.scenes.get(BAT_SCENE_NAME)
    if not bat_scene is None:
        render_scene(bat_scene, False)

    res = remove_bat_scene()
    message = ''

    return (res, message)


def setup_camera(cam_data: dict[str, float|int]) -> None:
    '''Setup BAT camera, given a dict containing camera data

    Args
        cam_data: dict containing camera data
    '''
    scene = bpy.context.scene
    scene.bat_properties.camera.sensor_width = cam_data.get('sensor_width', scene.bat_properties.camera.sensor_width)
    scene.bat_properties.camera.fx = cam_data.get('fx', scene.bat_properties.camera.fx)
    scene.bat_properties.camera.fy = cam_data.get('fy', scene.bat_properties.camera.fy)
    scene.bat_properties.camera.px = cam_data.get('cx', scene.bat_properties.camera.px)
    scene.bat_properties.camera.py = cam_data.get('cy', scene.bat_properties.camera.py)
    scene.bat_properties.camera.p1 = cam_data.get('p1', scene.bat_properties.camera.p1)
    scene.bat_properties.camera.p2 = cam_data.get('p2', scene.bat_properties.camera.p2)
    scene.bat_properties.camera.k1 = cam_data.get('k1', scene.bat_properties.camera.k1)
    scene.bat_properties.camera.k2 = cam_data.get('k2', scene.bat_properties.camera.k2)
    scene.bat_properties.camera.k3 = cam_data.get('k3', scene.bat_properties.camera.k3)
    scene.bat_properties.camera.k4 = cam_data.get('k4', scene.bat_properties.camera.k4)
    scene.bat_properties.camera.upscale_factor = cam_data.get('upscale_factor', scene.bat_properties.camera.upscale_factor)


def set_object_pose(object_name: str, location: list[float]|None=None, rotation: list[float]|None=None) -> None:
    '''Pose given object

    Args
        object_name: The name of the object
        location: List of object coordinates (x,y,z)
        rotation: Rotation of the object, using Euler angles measured in radians
    '''
    obj = bpy.data.objects.get(object_name)
    if obj:
        if location:
            obj.location = location
        if rotation:
            obj.rotation_euler = rotation


def distort(vec: np.array, intr: np.array, distortion_params:np.array) -> tuple[np.array,np.array]:
    '''
    Get distorted image coordinates from undistorted coordinates

    Args:
        vec: NumPy array containing undistorted image coordinates. Should be of shape (2,w*h),
            where "w" is the width and "h" is the height of the image. The first element along the first dimesion
            should hold the y coordinates (along height) and the second element of the first dimension should contain
            the x coordinates (along width). The [0,0] point should be upper left corner (so the first element of both
            the y and the x coordinates should be 0)
        intr: NumPy array containing camera intrinsics (fx,fy,px,py)
        distortion_params: NumPy array containing lens distortion parameters (p1,p2,k1,k2,k3,k4)

    Returns:
        dvec: Distorted image coordinates corresponding to the coordinates in "vec". It is a tuple of the x and y coordinates
    '''
    # Unpack values from inputs
    y,x = vec
    fx,fy,px,py = intr
    p1,p2,k1,k2,k3,k4 = distortion_params

    # Normalize image coordinates
    x = (x-px)/fx
    y = (y-py)/fy

    # Get intermediate coefficients
    x2 = x * x
    y2 = y * y
    xy2 = 2 * x * y
    r2 = x2 + y2
    r_coeff = 1 + (((k4 * r2 + k3) * r2 + k2) * r2 + k1) * r2
    tx = p1 * (r2 + 2 * x2) + p2 * xy2
    ty = p2 * (r2 + 2 * y2) + p1 * xy2

    # Distorted normalized coordinates
    xd = x * r_coeff + tx
    yd = y * r_coeff + ty

    # Distorted image coordinates
    image_x = fx * xd + px
    image_y = fy * yd + py
    return (image_x,image_y)


def interpolate(x: np.ndarray, mask: np.ndarray, flip: int, falloff: int = 1) -> np.ndarray:
    '''Interpolate missing values in x following a meandering pattern

    Args
        x: 2D NumPy array with missing/incorrect values (shape: (W,H), dtype: int or float)
        mask: 2D NumPy array telling which values of x to use for interpolation (shape: (W,H) must match with x.shape, dtype: bool)
            "True" elements signal that the corresponding values in x should be kept
        flip: Decides the direction of the meandering pattern (1=forward, 0=backward)
        falloff: Decides how much proximity influences interpolation (1=linear, 2=quadratic, ...)
    
    Returns
        The array with missing values filled. If a value cannot be determined (at the beginning and end of meander) it will be np.nan
    '''
    # Make a copy of the arrays that can be modified
    x_copy = np.copy(x)
    mask_copy = np.copy(mask)

    # Flip every second row starting from "flip", so the arrays can be flattened in a meander pattern
    x_copy[flip::2, :] = x_copy[flip::2, ::-1]
    mask_copy[flip::2, :] = mask_copy[flip::2, ::-1]

    # Flatten the arrays
    x_copy = x_copy.flatten()
    mask_copy = mask_copy.flatten()

    # Get indices where the mask is "True" and create an array containing all possible indices (xs)
    ind = np.where(mask_copy)[0]
    xs = np.arange(x_copy.size)

    # Get interpolated values at "xs", given the values in the flattened array (x_copy) at "ind"
    # Make values that could not be interpolated np.nan and reshape the resulted array
    inter = np.reshape(np.interp(xs,ind,x_copy[ind], left=np.nan, right=np.nan), x.shape)

    # Get closest left and right elements of "ind" for each element in xs
    l = np.insert(ind,ind.size,ind[-1])[np.searchsorted(ind,xs,side='left')]
    r = np.insert(ind,0,ind[0])[np.searchsorted(ind,xs,side='right')]

    # Calculate minimum distance of elements in "xs" from elements in "ind"
    # Use 1/(dist+1) to create weights
    # Reshape the resulted array and apply falloff
    weights = np.power(np.reshape(1/(np.min(np.stack((np.abs(xs-l),np.abs(xs-r))),axis=0)+1),x.shape), falloff)
    
    # Flip every second row starting from "flip", so the array elements correspond to elements in "x"
    inter[flip::2, :] = inter[flip::2, ::-1]
    weights[flip::2, :] = weights[flip::2, ::-1]

    return inter, weights


def fill_missing_values(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    '''Fill missing elements in x by applying the meandering interpolation in all four directions

    Args
        x: 2D NumPy array with missing/incorrect values (shape: (W,H), dtype: int or float)
        mask: 2D NumPy array telling which values of x to use for interpolation (shape: (W,H) must match with x.shape, dtype: bool)
            "True" elements signal that the corresponding values in x should be kept
    
    Returns
        The array with missing values filled.
    '''
    # Apply the meandering interpolation forward and backward, going row-by-row
    i1,w1 = interpolate(x,mask,0)
    i2,w2 = interpolate(x,mask,1)

    # Apply the meandering interpolation forward and backward, going column-by-column
    i3,w3 = interpolate(x.T,mask.T,0)
    i4,w4 = interpolate(x.T,mask.T,1)

    # Transpose the results so the align with i1,i2, and w1,w2
    i3 = i3.T
    w3 = w3.T
    i4 = i4.T
    w4 = w4.T

    # Stack all interpolated values and associated weights
    inter = np.stack((i1,i2,i3,i4),axis=-1)
    weights = np.stack((w1,w2,w3,w4), axis=-1)

    # Return weighted average, ignoring np.nan values
    return np.nansum(inter*weights, axis=-1)/np.nansum(weights, axis=-1)


def generate_inverse_distortion_map(width: int, height: int, intr: np.array, distortion_params: np.array, upscale_factor: int) -> np.array:
    '''
    Generates an inverse distortion map for fast image distortion lookup

    Args:
        width: Width of the image
        height: Height of the image
        intr: NumPy array containing camera intrinsics (fx,fy,px,py)
        distortion_params: NumPy array containing lens distortion parameters (p1,p2,k1,k2,k3,k4)
    
    Returns:
        inv_distortion_map: NumPy array containing the inverse distorion map. The shape is (height,width,3)
        The last dimension is for the y and x coordinates and a flag that signals if the pixel needs to be set or not
    '''
    # Create empty inverse distortion map
    inv_distortion_map = np.zeros((height,width,2))
    changed_items = np.zeros((height,width,1))

    # Create image coordinates matrix
    coords = np.moveaxis(np.mgrid[0:height*upscale_factor,0:width*upscale_factor],[0],[2])/upscale_factor

    # Get distorted coordinates
    distorted_xs, distorted_ys = distort(np.reshape(np.moveaxis(coords, [2],[0]), (2,height*upscale_factor*width*upscale_factor)), intr, distortion_params)

    # Filter distorted an undistorted coordinates (only leave te ones that are inside the image after distortion)
    valid_indices = np.logical_and(np.logical_and(distorted_xs>=0,distorted_xs<width),np.logical_and(distorted_ys>=0,distorted_ys<height))
    distorted_xs = distorted_xs[valid_indices].astype(int)
    distorted_ys = distorted_ys[valid_indices].astype(int)
    coords = np.reshape(coords, (height*upscale_factor*width*upscale_factor, 2))[valid_indices]

    inv_distortion_map[distorted_ys,distorted_xs] = coords
    changed_items[distorted_ys,distorted_xs] = 1
    inv_distortion_map[:,:,0] = fill_missing_values(inv_distortion_map[:,:,0],changed_items.astype(bool)[:,:,0])
    inv_distortion_map[:,:,1] = fill_missing_values(inv_distortion_map[:,:,1],changed_items.astype(bool)[:,:,0])
    inv_distortion_map = np.append(inv_distortion_map, changed_items, axis=2)
    return inv_distortion_map