import os
import json
import bpy
from . import constants, common
from bpy.types import Material, World, Scene


# -------------------------------
# BAT class functions

def set_default_class_name(scene: Scene) -> None:
    '''
    Set the default class name for list of classes ('Background' class)

    Args
        scene: Scene in which the change will be applied
    '''
    classes = scene.bat_properties.classification_classes
    # set default value if the list of classes is empty
    if not classes:
        background_class = classes.add()
        background_class.name = constants.DEFAULT_CLASS_NAME
        background_class.mask_color = (0.0,0.0,0.0,1.0)


# -------------------------------
# BAT scene functions

def add_empty_world(world: World, scene: Scene) -> None:
    '''
    Create an "empty" (dark) copy of the given world and link it to a scene

    Args
        world: Input world to copy settings from
        scene: Scene to which the empty world will be linked
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


def apply_render_settings(scene: Scene) -> None:
    '''
    Apply render settings for scene for segmentation mask rendering

    Args
        scene: Scene to apply the render settings to
    '''
    # Create a new ViewLayer for BAT
    bat_view_layer = scene.view_layers.new(constants.BAT_VIEW_LAYER_NAME)
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


def apply_output_settings(scene: Scene, output_format: constants.OutputFormat=constants.OutputFormat.PNG) -> None:
    '''
    Apply output settings for scene

    Args
        scene: Scene to apply the output settings to
        output_format: Output file format
    '''
    # Set output file format
    scene.render.image_settings.file_format = output_format
    scene.render.image_settings.color_mode = 'RGBA'
    match output_format:
        case constants.OutputFormat.PNG:
            scene.render.image_settings.color_depth = constants.ColorDepth.HALF
            scene.render.image_settings.compression = 0
        case constants.OutputFormat.OPEN_EXR:
            scene.render.image_settings.color_depth = constants.ColorDepth.FULL

    # Set output file path
    if '.' in scene.render.filepath:
        filepath = os.path.dirname(scene.render.filepath)
    else:
        filepath = scene.render.filepath
    filepath += '/annotations/'
    
    scene.render.filepath = filepath


def make_mask_material(material_name: str) -> Material:
    '''
    Create material for making segmentation masks

    Args
        material_name: The name of the new material

    Returns:
        The created material
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


def export_class_info() -> set[str]:
    '''
    Set the "Note" metadata for the render output
    '''
    class_info = {}
    class_info['0'] = constants.DEFAULT_CLASS_NAME
    bat_scene = bpy.data.scenes.get(constants.BAT_SCENE_NAME)
    if not bat_scene is None:
        for classification_class in bat_scene.bat_properties.classification_classes:
            mask_material = bpy.data.materials.get(constants.BAT_SEGMENTATION_MASK_MAT_NAME+'_'+classification_class.name)
            if not mask_material is None:
                class_info[mask_material.pass_index] = classification_class.name
        bat_scene.render.stamp_note_text = json.dumps(class_info)
    return {'FINISHED'}


def setup_compositor(scene: Scene) -> None:
    '''
    Set up the compositor workspace of the BAT scene

    Args
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
    render_layers_node.layer = constants.BAT_VIEW_LAYER_NAME

    compositor_node = scene.node_tree.nodes.new('CompositorNodeComposite')

    inv_distortion_map = bpy.data.images.get(constants.INV_DISTORTION_MAP_NAME)
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
    file_output_node.format.file_format = constants.OutputFormat.OPEN_EXR
    file_output_node.format.color_mode = 'RGBA'
    file_output_node.format.color_depth = constants.ColorDepth.FULL
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
        file_output_node.file_slots.new(constants.INV_DISTORTION_MAP_NAME)
        scene.node_tree.links.new(image_node.outputs['Image'], flip_node.inputs['Image'])
        scene.node_tree.links.new(flip_node.outputs['Image'], file_output_node.inputs[constants.INV_DISTORTION_MAP_NAME])


def setup_bat_scene() -> tuple[set[str],str]:
    '''
    Set up a separate scene for BAT
    '''
    active_scene = bpy.context.scene
    bat_scene = bpy.data.scenes.get(constants.BAT_SCENE_NAME)

    # Create the BAT scene if it does not exist yet
    if bat_scene is None:
        bat_scene = active_scene.copy()
        bat_scene.name = constants.BAT_SCENE_NAME

    
    # Add an empty world (no HDRI, no world lighting ...)
    add_empty_world(active_scene.world, bat_scene)


    # Render settings
    apply_render_settings(bat_scene)

    # Image output settings (we use OpenEXR Multilayer)
    apply_output_settings(bat_scene, constants.OutputFormat.OPEN_EXR)


    # Unlink all collections and objects from BAT scene
    for coll in bat_scene.collection.children:
        bat_scene.collection.children.unlink(coll)
    for obj in bat_scene.collection.objects:
        bat_scene.collection.objects.unlink(obj)
        

    # Link needed collections/objects to BAT scene
    for class_index, classification_class in enumerate([c for c in bat_scene.bat_properties.classification_classes if c.name != constants.DEFAULT_CLASS_NAME]):

        # Create a material for segmentation masks
        mask_material = make_mask_material(constants.BAT_SEGMENTATION_MASK_MAT_NAME+'_'+classification_class.name)
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
        root_objects = list({common.find_root(o) for o in orig_coll_objects})

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
    '''
    Remove BAT Scene
    '''
    bat_scene = bpy.data.scenes.get(constants.BAT_SCENE_NAME)

    if not bat_scene is None:
        # Remove objects, collections, world and material:
        for obj in bat_scene.objects:
            bpy.data.objects.remove(obj)
        for coll in bat_scene.collection.children_recursive:
            bpy.data.collections.remove(coll)
        bpy.data.worlds.remove(bat_scene.world)
        segmentation_mask_material = bpy.data.materials.get(constants.BAT_SEGMENTATION_MASK_MAT_NAME)
        if segmentation_mask_material:
            bpy.data.materials.remove(segmentation_mask_material)
        bpy.data.scenes.remove(bat_scene)

    return {'FINISHED'}


# -------------------------------
# Render BAT annotations

def bat_render_annotation() -> tuple[set[str], str]:
    '''
    Render annotations with BAT
    '''
    res, message = setup_bat_scene()
    if res == {"CANCELLED"}:
        return (res, message)

    bat_scene = bpy.data.scenes.get(constants.BAT_SCENE_NAME)
    if not bat_scene is None:
        common.render_scene(bat_scene, False)

    res = remove_bat_scene()
    message = ''

    return (res, message)