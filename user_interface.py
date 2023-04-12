import bpy
from . import utils

DEFAULT_CLASS_NAME = utils.DEFAULT_CLASS_NAME

# Main panel for user interaction
class BAT_PT_main_panel(bpy.types.Panel):
    """BAT Panel"""
    bl_idname = 'VIEW_3D_PT_BAT_Panel'
    bl_label = 'BAT Panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BAT'
    
    def draw(self, context):
        layout = self.layout

        # Current class visualization
        box = layout.box()
        box.label(text='Current class')
        row = box.row(align=True)
        row.prop(context.scene.bat_properties, 'current_class', text='')
        row.operator("bat.add_class", text="", icon="ADD")
        row.operator("bat.remove_class", text="", icon="REMOVE")
        box.label(text='Properties')
        row = box.row(align=True)
        if context.scene.bat_properties.current_class == DEFAULT_CLASS_NAME or context.scene.bat_properties.current_class_is_instances:
            row.enabled = False
        row.prop(context.scene.bat_properties, 'current_class_color', text='Mask color')
        row = box.row(align=True)
        if context.scene.bat_properties.current_class == DEFAULT_CLASS_NAME:
            row.enabled = False
        row.prop_search(context.scene.bat_properties, "current_class_objects", bpy.data, "collections", text='Objects')
        row = box.row(align=True)
        if context.scene.bat_properties.current_class == DEFAULT_CLASS_NAME:
            row.enabled = False
        row.prop(context.scene.bat_properties, 'current_class_is_instances', text='Instance segmentation')

        layout.row().separator()

        # Output properties
        layout.label(text='Output properties')
        row = layout.row()
        row.prop(context.scene.bat_properties, 'save_annotation', text='Save annotations')
        row = layout.row()
        row.operator('render.bat_render_annotation', text='Render annotation', icon='RENDER_STILL')
        row = layout.row()
        row.operator('render.bat_render_animation', text='Render animation', icon='RENDER_ANIMATION')


# -------------------------------
# Register/Unregister

classes = [BAT_PT_main_panel]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()