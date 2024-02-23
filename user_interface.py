import bpy
from . import utils
from bpy.types import Context

# Main panel for user interaction
class BAT_PT_main_panel(bpy.types.Panel):
    """BAT Panel"""
    bl_idname = 'VIEW_3D_PT_BAT_Panel'
    bl_label = 'BAT Panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BAT'
    
    def draw(self, context: Context) -> None:
        '''
        Draw BAT panel

        Args:
            context : Current context
        '''

        layout = self.layout

        # -------------------------------
        # Current class visualization
        box = layout.box()

        # Class selector row
        box.label(text='Current class')
        row = box.row(align=True)
        row.prop(context.scene.bat_properties, 'current_class', text='')
        row.operator("bat.add_class", text="", icon="ADD")
        row.operator("bat.remove_class", text="", icon="REMOVE")

        # Class properties rows
        box.label(text='Properties')
        row = box.row(align=True)
        if context.scene.bat_properties.current_class == utils.DEFAULT_CLASS_NAME:
            row.enabled = False
        row.prop(context.scene.bat_properties, 'current_class_color', text='Mask color')
        row = box.row(align=True)
        if context.scene.bat_properties.current_class == utils.DEFAULT_CLASS_NAME:
            row.enabled = False
        row.prop_search(context.scene.bat_properties, "current_class_objects", bpy.data, "collections", text='Objects')
        row = box.row(align=True)
        if context.scene.bat_properties.current_class == utils.DEFAULT_CLASS_NAME:
            row.enabled = False
        row.prop(context.scene.bat_properties, 'current_class_is_instances', text='Instance segmentation')

        # -------------------------------
        # Data passes
        row = box.row(align=True)
        if context.scene.bat_properties.current_class == utils.DEFAULT_CLASS_NAME:
            row.enabled = False
        row.prop(context.scene.bat_properties, 'depth_map_generation', text='Depth map')
        row = box.row(align=True)
        if context.scene.bat_properties.current_class == utils.DEFAULT_CLASS_NAME:
            row.enabled = False
        row.prop(context.scene.bat_properties, 'surface_normal_generation', text='Surface normal')
        row = box.row(align=True)
        if context.scene.bat_properties.current_class == utils.DEFAULT_CLASS_NAME:
            row.enabled = False
        row.prop(context.scene.bat_properties, 'optical_flow_generation', text='Optical flow')

        layout.row().separator()

        # -------------------------------
        # Output properties
        layout.label(text='Output properties')
        row = layout.row()
        row.prop(context.scene.bat_properties, 'save_annotation', text='Save annotations')
        row = layout.row()
        row.prop(context.scene.bat_properties, 'export_class_info', text='Export class info')
        row = layout.row()
        row.operator('render.bat_render_annotation', text='Render annotation', icon='RENDER_STILL')



# Sub-panel for camera calibration in and output
class BAT_PT_camera_panel(bpy.types.Panel):
    """BAT Camera"""
    bl_idname = 'VIEW_3D_PT_BAT_Camera'
    bl_label = 'BAT Camera'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BAT'
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context: Context) -> None:
        '''
        Draw BAT Camera panel

        Args:
            context : Current context
        '''

        layout = self.layout
        row = layout.row()
        row.prop(context.scene.bat_properties.camera, 'sensor_width', text='Sensor Width')

        # -------------------------------
        # Intrinsic parameters
        box = layout.box()
        box.label(text='Intrinsic parameters')
        row = box.row(align=True)
        row.label(text='Focal Length X')
        row.prop(context.scene.bat_properties.camera, 'fx', text='')
        row = box.row(align=True)
        row.label(text='Focal Length Y')
        row.prop(context.scene.bat_properties.camera, 'fy', text='')
        row = box.row(align=True)
        row.label(text='Optical Center X')
        row.prop(context.scene.bat_properties.camera, 'px', text='')
        row = box.row(align=True)
        row.label(text='Optical Center Y')
        row.prop(context.scene.bat_properties.camera, 'py', text='')

        # -------------------------------
        # Lens distortion parameters
        box = layout.box()
        box.label(text='Lens Distortion')
        row = box.row(align=True)
        row.label(text='p1')
        row.prop(context.scene.bat_properties.camera, 'p1', text='')
        row = box.row(align=True)
        row.label(text='p2')
        row.prop(context.scene.bat_properties.camera, 'p2', text='')
        box.row().separator()
        row = box.row(align=True)
        row.label(text='k1')
        row.prop(context.scene.bat_properties.camera, 'k1', text='')
        row = box.row(align=True)
        row.label(text='k2')
        row.prop(context.scene.bat_properties.camera, 'k2', text='')
        row = box.row(align=True)
        row.label(text='k3')
        row.prop(context.scene.bat_properties.camera, 'k3', text='')
        row = box.row(align=True)
        row.label(text='k4')
        row.prop(context.scene.bat_properties.camera, 'k4', text='')

        # -------------------------------
        # Create/Update distortion map
        layout.row().separator()
        row = layout.row()
        row.operator('bat.generate_distortion_map', text='Create/Update Distortion Map', icon='IMAGE_DATA')


# -------------------------------
# Register/Unregister

classes = [BAT_PT_main_panel, BAT_PT_camera_panel]

def register() -> None:
    '''
    Register UI elements
    '''
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister() -> None:
    '''
    Unregister UI elements
    '''
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()