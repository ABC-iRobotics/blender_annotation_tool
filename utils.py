import bpy
import numpy as np
from enum import Enum
import time

from collections.abc import Callable, Iterator
from bpy.types import Collection, Material, World, Scene, Context

DEFAULT_CLASS_NAME = 'Background'
BAT_SCENE_NAME = 'BAT_Scene'
BAT_SEGMENTATION_MASK_MAT_NAME = 'BAT_segmentation_mask'

class Pass_Enum(Enum):
    DEPTH = 'Depth'
    VECTOR = 'Vector'
    NORMAL = 'Normal'


def instance_color_gen(base_color: list[float]) -> Iterator[list[float]]:
    '''
    Make a generator for creating instance colors from a single base color

    Args:
        base_color : Base color (RGB) to initiate the generator with

    Returns:
        gen : A generator to generate new colors for new instances
    '''
    for i in range(255):
        base_color[3] = (i+1)/255
        yield base_color
    

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

    # Add nodes
    obj_info_node = mask_material.node_tree.nodes.new('ShaderNodeObjectInfo')
    emission_shader_node = mask_material.node_tree.nodes.new('ShaderNodeEmission')
    matrial_output_node = mask_material.node_tree.nodes.new('ShaderNodeOutputMaterial')
    matrial_output_node.is_active_output = True

    # Create links
    mask_material.node_tree.links.new(emission_shader_node.inputs['Color'], obj_info_node.outputs['Color'])
    mask_material.node_tree.links.new(matrial_output_node.inputs['Surface'], emission_shader_node.outputs['Emission'])
    emission_shader_node.inputs['Strength'].default_value = 100

    return mask_material



def setup_bat_scene(context: Context, bat_scene_name: str, report_func: Callable[[set[str], str], None]) -> None:
    '''
    Set up a separate scene for BAT

    All data is linked except for objects that are associated to classes

    Args:
        context : Current context
        bat_scene_name : Name for the scene BAT will use
        report_func : Report function of operator to display errors
    '''
    active_scene = context.scene

    # Create the BAT scene if it does not exist yet
    if bat_scene_name not in [s.name for s in bpy.data.scenes]:
        bat_scene = active_scene.copy()
        bat_scene.name = bat_scene_name
    else:
        bat_scene = bpy.data.scenes[bat_scene_name]

    
    add_empty_world(active_scene.world, bat_scene)

    mask_material = make_mask_material(BAT_SEGMENTATION_MASK_MAT_NAME)

    # Use the Cycles render engine
    bat_scene.render.engine = 'CYCLES'
    # Raw view transform so colors will be the same as in BAT
    bat_scene.view_settings.view_transform = 'Raw'
    # Disable anti aliasing
    bat_scene.cycles.filter_width = 0.01
    bat_scene.cycles.use_denoising = False

    # Image output settings
    bat_scene.render.image_settings.file_format = 'PNG'
    bat_scene.render.image_settings.color_depth = '16'
    bat_scene.render.image_settings.color_mode = 'RGBA'
    bat_scene.render.image_settings.compression = 0

    
    # Unlink all collections and objects
    for coll in bat_scene.collection.children:
        bat_scene.collection.children.unlink(coll)
    for obj in bat_scene.collection.objects:
        bat_scene.collection.objects.unlink(obj)

    bat_scene.collection.objects.link(active_scene.camera)
        

    # Link needed collections/objects to BAT scene
    for classification_class in [c for c in bat_scene.bat_properties.classification_classes if c.name != DEFAULT_CLASS_NAME]:
        # Get original collection and create a new one in the BAT scene for each
        # classification class
        orig_collection = bpy.data.collections.get(classification_class.objects)
        if orig_collection is None:
            # If the collection is deleted or renamed in the meantime
            report_func({'ERROR'},'Could not find collection {}!'.format(classification_class.objects))
            orig_collection = bpy.data.collections.get(classification_class.objects)
        new_collection = bpy.data.collections.new(classification_class.name)
        bat_scene.collection.children.link(new_collection)

        class_instance_color_gen = instance_color_gen(list(classification_class.mask_color))

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
            elif classification_class.is_instances:
                try:
                    color = next(class_instance_color_gen)
                    obj_copy.color = color
                    
                except StopIteration:
                    report_func({'ERROR_INVALID_INPUT'}, 'Too many instances, not enough color codes!')
            
            


def render_segmentation_masks(scene, instance_color_gen, self):
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

def get_depth_image(scene):

    if scene.bat_properties.depth_map_generation:
        original_render_engine = scene.render.engine
        scene.render.engine = 'CYCLES'
        
        new_view_layer(scene, Pass_Enum.DEPTH)

        original_filepath = scene.render.filepath

        if '.' in scene.render.filepath:
            filepath = scene.render.filepath
        else:
            filepath = scene.render.frame_path(frame=scene.frame_current)
        filepath = ''.join(filepath.split('.')[:-1]) + '_depth_map'
        
        scene.render.filepath = filepath

        map = get_render_result(scene)
        map = map[:,:,0]

        if scene.bat_properties.save_annotation:
            np.save(filepath, map)

        scene.render.filepath = original_filepath
        scene.render.engine = original_render_engine

def get_optical_flow(scene):

    if scene.bat_properties.optical_flow_generation:
        original_render_engine = scene.render.engine
        scene.render.engine = 'CYCLES'

        new_view_layer(scene, Pass_Enum.VECTOR)

        original_filepath = scene.render.filepath

        if '.' in scene.render.filepath:
            filepath = scene.render.filepath
        else:
            filepath = scene.render.frame_path(frame=scene.frame_current)
        filepath = ''.join(filepath.split('.')[:-1]) + '_optical_flow'
        
        scene.render.filepath = filepath

        map = get_render_result(scene)
        map = map[:,:,2:]

        if scene.bat_properties.save_annotation:
            np.save(filepath, map)

        scene.render.filepath = original_filepath
        scene.render.engine = original_render_engine

def get_surface_normal(scene):

    if scene.bat_properties.surface_normal_generation:
        original_render_engine = scene.render.engine
        scene.render.engine = 'CYCLES'
        
        new_view_layer(scene, Pass_Enum.NORMAL)

        original_filepath = scene.render.filepath

        if '.' in scene.render.filepath:
            filepath = scene.render.filepath
        else:
            filepath = scene.render.frame_path(frame=scene.frame_current)
        filepath = ''.join(filepath.split('.')[:-1]) + '_surface_normal'
        
        scene.render.filepath = filepath

        map = get_render_result(scene)

        if scene.bat_properties.save_annotation:
            np.save(filepath, map)

        scene.render.filepath = original_filepath
        scene.render.engine = original_render_engine

def get_render_result(scene):

    original_motion_blur = scene.render.use_motion_blur
    scene.render.use_motion_blur = False
    orogonal_denoising = scene.cycles.use_denoising
    scene.cycles.use_denoising = False
    original_samples = scene.cycles.samples
    scene.cycles.samples = 1
    original_preview_samples = scene.cycles.preview_samples
    scene.cycles.preview_samples = 1
    
    bpy.ops.render.render(animation=False, write_still=False, use_viewport=False, layer="", scene="")

    scene.render.use_motion_blur = original_motion_blur
    scene.cycles.use_denoising = orogonal_denoising
    scene.cycles.samples = original_samples
    scene.cycles.preview_samples = original_preview_samples

    viewer = bpy.data.images['Viewer Node']
    w, h = viewer.size
    img = np.array(viewer.pixels[:], dtype=np.float32)
    img = np.reshape(img, (h, w, 4))[:,:,:]
    img = np.flipud(img)
    return img

def new_view_layer(scene, pass_enum):
    scene.use_nodes = True

    for node in scene.node_tree.nodes:
        if isinstance(node, bpy.types.CompositorNodeViewer):
            scene.node_tree.nodes.remove(node)
    
    if scene.view_layers.find('BATViewLayer') == -1:
        scene.view_layers.new('BATViewLayer')

        collections = []  
        for classification_class in scene.bat_properties.classification_classes:
            if classification_class.objects != '':
                collections.append(classification_class.objects)

        for c in scene.view_layers['BATViewLayer'].layer_collection.children:
            if c.name not in collections:
                c.exclude = True
    
        obj = scene.camera
        for x in obj.users_collection:
            for i in scene.view_layers['BATViewLayer'].layer_collection.children:
                if i.collection  == x:
                    i.exclude = False

    if scene.node_tree.nodes.find('BAT_Frame') == -1:
        frame = scene.node_tree.nodes.new('NodeFrame')
        frame.name = 'BAT_Frame'
        frame.label = 'BAT'
    else:
        frame = scene.node_tree.nodes['BAT_Frame']

    nodes = []

    if scene.node_tree.nodes.find('RLayersBAT') == -1:
        render_layers_node_for_BAT = scene.node_tree.nodes.new('CompositorNodeRLayers')
        render_layers_node_for_BAT.name = 'RLayersBAT'
        nodes.append(render_layers_node_for_BAT)
    else:
        render_layers_node_for_BAT = scene.node_tree.nodes['RLayersBAT']
        nodes.append(render_layers_node_for_BAT)

    if pass_enum == Pass_Enum.DEPTH:
        scene.view_layers['BATViewLayer'].use_pass_z = True
    if pass_enum == Pass_Enum.VECTOR:
        scene.view_layers['BATViewLayer'].use_pass_vector = True
    if pass_enum == Pass_Enum.NORMAL:
        scene.view_layers['BATViewLayer'].use_pass_normal = True

    if scene.node_tree.nodes.find('BATViewer') == -1:
        viewer_node = scene.node_tree.nodes.new('CompositorNodeViewer')
        viewer_node.name = "BATViewer"
        nodes.append(viewer_node)
    else:
        viewer_node = scene.node_tree.nodes["BATViewer"]
    
    render_layers_node_for_BAT.layer = "BATViewLayer"
    link_viewer_render = scene.node_tree.links.new(render_layers_node_for_BAT.outputs[pass_enum.value], viewer_node.inputs['Image'])

    for n in nodes:
        n.parent = scene.node_tree.nodes['BAT_Frame']

def view_layer_teardown(scene):
    if scene.node_tree.nodes.find('BAT_Frame') != -1 and scene.view_layers.find('BATViewLayer') != -1:
        for node in scene.node_tree.nodes:
            if node.parent == scene.node_tree.nodes['BAT_Frame']:
                scene.node_tree.nodes.remove(node)
        scene.node_tree.nodes.remove(scene.node_tree.nodes['BAT_Frame'])
        scene.view_layers.remove(scene.view_layers['BATViewLayer'])

def get_annotations(scene):
    
    get_depth_image(scene)
    get_surface_normal(scene)
    get_optical_flow(scene)

    view_layer_teardown(scene)