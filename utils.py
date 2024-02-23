import os
import bpy
import numpy as np
from enum import Enum
from bpy.types import Collection, Material, World, Scene


# -------------------------------
# Constants

DEFAULT_CLASS_NAME = 'Background'
BAT_SCENE_NAME = 'BAT_Scene'
BAT_VIEW_LAYER_NAME = 'BAT_ViewLayer'
BAT_SEGMENTATION_MASK_MAT_NAME = 'BAT_segmentation_mask'


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


def render_scene(scene: Scene) -> None:
    '''
    Render scene

    Args:
        scene : Scene to render
    '''
    # Set file name
    render_filepath_temp = scene.render.filepath
    scene.render.filepath = scene.render.frame_path(frame=scene.frame_current)

    # Render image
    bpy.ops.render.render(write_still=scene.bat_properties.save_annotation, scene=scene.name)

    # Reset output path
    scene.render.filepath = render_filepath_temp

    # Export class info if needed
    if scene.bat_properties.export_class_info:
        bpy.ops.bat.export_class_info()


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


def generate_inverse_distortion_map(width: int, height: int, intr: np.array, distortion_params: np.array, upscale_factor: int) -> np.array:
    '''
    Generates an inverse distortion map for fast image distortion lookup

    Args:
        width: Width of the image
        height: Height of the image
        intr: NumPy array containing camera intrinsics (fx,fy,px,py)
        distortion_params: NumPy array containing lens distortion parameters (p1,p2,k1,k2,k3,k4)
    
    Returns:
        inv_distortion_map: NumPy array containing the inverse distorion map. The shape is (height,width,2)
        The last dimension is for the y and x coordinates respectively
    '''
    # Create empty inverse distortion map
    inv_distortion_map = np.zeros((height,width,2))

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
    return inv_distortion_map