import os
import bpy
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