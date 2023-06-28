import bpy
import numpy as np

DEFAULT_CLASS_NAME = "Background"

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

    original_render_engine = scene.render.engine
    scene.render.engine = 'CYCLES'

    scene.view_layers['ViewLayer'].use_pass_z = True

    scene.use_nodes = True
    for node in scene.node_tree.nodes:
        scene.node_tree.nodes.remove(node)
    render_layers_node = scene.node_tree.nodes.new('CompositorNodeRLayers')
    viewer_node = scene.node_tree.nodes.new('CompositorNodeViewer')
    composite_node = scene.node_tree.nodes.new('CompositorNodeComposite')
    link_viewer_render = scene.node_tree.links.new(render_layers_node.outputs["Depth"], viewer_node.inputs['Image'])
    link_composite_render = scene.node_tree.links.new(render_layers_node.outputs["Image"], composite_node.inputs['Image'])

    original_filepath = scene.render.filepath

    if '.' in scene.render.filepath:
        filepath = scene.render.filepath
    else:
        filepath = scene.render.frame_path(frame=scene.frame_current)
    filepath = ''.join(filepath.split('.')[:-1]) + '_depth_map'
    
    scene.render.filepath = filepath

    map = get_render_result()

    if scene.bat_properties.save_annotation:
        np.save(filepath, map)

    scene.render.filepath = original_filepath
    scene.render.engine = original_render_engine

def get_optical_flow(scene):

    original_render_engine = scene.render.engine
    scene.render.engine = 'CYCLES'
    
    scene.view_layers['ViewLayer'].use_pass_vector = True

    scene.use_nodes = True
    for node in scene.node_tree.nodes:
        scene.node_tree.nodes.remove(node)
    render_layers_node = scene.node_tree.nodes.new('CompositorNodeRLayers')
    viewer_node = scene.node_tree.nodes.new('CompositorNodeViewer')
    composite_node = scene.node_tree.nodes.new('CompositorNodeComposite')
    link_viewer_render = scene.node_tree.links.new(render_layers_node.outputs["Vector"], viewer_node.inputs['Image'])
    link_composite_render = scene.node_tree.links.new(render_layers_node.outputs["Image"], composite_node.inputs['Image'])

    original_filepath = scene.render.filepath

    if '.' in scene.render.filepath:
        filepath = scene.render.filepath
    else:
        filepath = scene.render.frame_path(frame=scene.frame_current)
    filepath = ''.join(filepath.split('.')[:-1]) + '_optical_flow'
    
    scene.render.filepath = filepath

    map = get_render_result()

    if scene.bat_properties.save_annotation:
        np.save(filepath, map)

    scene.render.filepath = original_filepath
    scene.render.engine = original_render_engine

def get_surface_normal(scene):

    original_render_engine = scene.render.engine
    scene.render.engine = 'CYCLES'
    
    scene.view_layers['ViewLayer'].use_pass_normal = True

    scene.use_nodes = True
    for node in scene.node_tree.nodes:
        scene.node_tree.nodes.remove(node)
    render_layers_node = scene.node_tree.nodes.new('CompositorNodeRLayers')
    viewer_node = scene.node_tree.nodes.new('CompositorNodeViewer')
    composite_node = scene.node_tree.nodes.new('CompositorNodeComposite')
    link_viewer_render = scene.node_tree.links.new(render_layers_node.outputs["Normal"], viewer_node.inputs['Image'])
    link_composite_render = scene.node_tree.links.new(render_layers_node.outputs["Image"], composite_node.inputs['Image'])

    original_filepath = scene.render.filepath

    if '.' in scene.render.filepath:
        filepath = scene.render.filepath
    else:
        filepath = scene.render.frame_path(frame=scene.frame_current)
    filepath = ''.join(filepath.split('.')[:-1]) + '_surface_normal'
    
    scene.render.filepath = filepath

    map = get_render_result()

    if scene.bat_properties.save_annotation:
        np.save(filepath, map)

    scene.render.filepath = original_filepath
    scene.render.engine = original_render_engine

def get_render_result():

    bpy.ops.render.render(animation=False, write_still=False, use_viewport=False, layer="", scene="")

    viewer = bpy.data.images['Viewer Node']
    w, h = viewer.size
    img = np.array(viewer.pixels[:], dtype=np.float32)
    img = np.reshape(img, (h, w, 4))[:,:,:]
    img = np.flipud(img)
    return img