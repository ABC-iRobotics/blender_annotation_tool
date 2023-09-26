import bpy

# -------------------------------
# Utility functions

# Synchronize elements of Enum for current class with the list of classes
def populate_classes(self, context):
    
    Enum_items = [] 

    for classification_class in context.scene.bat_properties.classification_classes:
        
        name = classification_class.name
        item = (name, name, name)
        
        Enum_items.append(item)
        
    return Enum_items

# Update values of current class params when the current class is changed
def update_current_class_params(self, context):
    index = context.scene.bat_properties.classification_classes.find(context.scene.bat_properties.current_class)
    context.scene.bat_properties.current_class_color = context.scene.bat_properties.classification_classes[index].mask_color
    context.scene.bat_properties.current_class_objects = context.scene.bat_properties.classification_classes[index].objects
    context.scene.bat_properties.current_class_is_instances = context.scene.bat_properties.classification_classes[index].is_instances

# Update color of class in the list of classes if the color for the current class is changed
def update_classification_class_color(self, context):
    index = context.scene.bat_properties.classification_classes.find(context.scene.bat_properties.current_class)
    context.scene.bat_properties.classification_classes[index].mask_color = context.scene.bat_properties.current_class_color

# Update associated collection of class in the list of classes if the associated collection for the current class is changed
def update_classification_class_objects(self, context):
    index = context.scene.bat_properties.classification_classes.find(context.scene.bat_properties.current_class)
    context.scene.bat_properties.classification_classes[index].objects = context.scene.bat_properties.current_class_objects

# Update instance segmentation setup of class in the list of classes if the instance segmentation setup for the current class is changed
def update_classification_class_is_instances(self, context):
    index = context.scene.bat_properties.classification_classes.find(context.scene.bat_properties.current_class)
    context.scene.bat_properties.classification_classes[index].is_instances = context.scene.bat_properties.current_class_is_instances

#Update depth map annotation generation, wheter it is needed or not
def update_depth_map_generation(self, context):
    index = context.scene.bat_properties.classification_classes.find(context.scene.bat_properties.current_class)
    context.scene.bat_properties.classification_classes[index].depth_map = context.scene.bat_properties.depth_map_generation

#Update surface normal map annotation generation, wheter it is needed or not
def update_surface_normal_generation(self, context):
    index = context.scene.bat_properties.classification_classes.find(context.scene.bat_properties.current_class)
    context.scene.bat_properties.classification_classes[index].surface_normal = context.scene.bat_properties.surface_normal_generation

#Update optical flow annotation generation, wheter it is needed or not
def update_optical_flow_generation(self, context):
    index = context.scene.bat_properties.classification_classes.find(context.scene.bat_properties.current_class)
    context.scene.bat_properties.classification_classes[index].optical_flow = context.scene.bat_properties.optical_flow_generation

# -------------------------------
# Properties for describing a single class

class BAT_ClassificationClass(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(
        name="class_name",
        description="Identifier for the class"
    )
    mask_color: bpy.props.FloatVectorProperty(
        name="object_color",
        subtype='COLOR',
        default=(1.0, 1.0, 1.0),
        min=0.0, max=1.0,
        description="Color used for representing the class on the annotated image"
    )
    objects: bpy.props.StringProperty(
        name="class_objects",
        description="Name of a collection containing objects belonging to this class"
    )
    is_instances: bpy.props.BoolProperty(
        name="is_instances",
        description="If true the objects in the associated collection will be handled as instances (separate colors in annotation)"
    )
    depth_map: bpy.props.BoolProperty(
        name="depth_map",
        description="If true the depth map of the objects in the associated collection will be generated"
    )
    surface_normal: bpy.props.BoolProperty(
        name="surface_normal",
        description="If true the surface normal map of the objects in the associated collection will be generated"
    )
    optical_flow: bpy.props.BoolProperty(
        name="optical_flow",
        description="If true the optical flow of the objects in the associated collection will be generated"
    )


# -------------------------------
# Properties for visualisation (currently selected class)

class BAT_Properties(bpy.types.PropertyGroup):

    # Collection of classes (list of classes)
    classification_classes: bpy.props.CollectionProperty(type=BAT_ClassificationClass)

    # The currently selected class
    current_class: bpy.props.EnumProperty(items=populate_classes, update=update_current_class_params)

    # Properties of currently selected class
    current_class_color: bpy.props.FloatVectorProperty(
        name="Mask color",
        subtype='COLOR',
        default=(0.0, 0.0, 0.0),
        min=0.0, max=1.0,
        description="Color value of the current class for the segmentation mask",
        update=update_classification_class_color
    )
    current_class_objects: bpy.props.StringProperty(
        name="Objects' collection",
        description="Collection containing all objects belonging to the current class",
        update=update_classification_class_objects
    )
    current_class_is_instances: bpy.props.BoolProperty(
        name="Is instances?",
        description="Objects of this class are instances (instance segmentation)",
        default=False,
        update=update_classification_class_is_instances
    )
    depth_map_generation: bpy.props.BoolProperty(
        name="generate depth map?",
        description="Generate the depth map of this class",
        default=False,
        update=update_depth_map_generation
    )
    surface_normal_generation: bpy.props.BoolProperty(
        name="generate surface normal?",
        description="Generate the surface normal of this class",
        default=False,
        update=update_surface_normal_generation
    )
    optical_flow_generation: bpy.props.BoolProperty(
        name="generate optical flow?",
        description="Generate the optical flow of this class",
        default=False,
        update=update_optical_flow_generation
    )

    # Output properties
    save_annotation: bpy.props.BoolProperty(
        name='Save annotations',
        description="Save the annotations whenever a render made",
        default=True
    )


# -------------------------------
# Register/Unregister

classes = [BAT_ClassificationClass, BAT_Properties]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bat_properties = bpy.props.PointerProperty(type=BAT_Properties)

def unregister():
    del bpy.types.Scene.bat_properties
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
