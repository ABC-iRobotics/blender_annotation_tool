import bpy
import numpy as np
from enum import Enum
import time

DEFAULT_CLASS_NAME = "Background"

class Pass_Enum(Enum):
    DEPTH = 'Depth'
    VECTOR = 'Vector'
    NORMAL = 'Normal'

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

    for classification_class in scene.bat_properties.classification_classes:
        if classification_class.depth_map:
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

    for classification_class in scene.bat_properties.classification_classes:
        if classification_class.optical_flow:
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

    for classification_class in scene.bat_properties.classification_classes:
        if classification_class.surface_normal:
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