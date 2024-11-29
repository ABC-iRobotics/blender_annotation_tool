import bpy
from bpy.types import Collection, Object, Scene


# -------------------------------
# Common functions that can be used without BAT

def find_parent_collection(root_collection: Collection, collection: Collection) -> Collection | None:
    '''
    Recursive function to find and return parent collection of given collection

    Args
        root_collection : Root collection to start the search from
        collection: Collection to look for

    Returns
        Parent of "collection" if "collection" exists in the tree, else None
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

    Args
        obj: The object for which the root parent is sought

    Returns
        The root object
    '''
    if obj.parent is None:
        return obj
    else:
        return find_root(obj.parent)


def set_object_pose(object_name: str, location: list[float]|None=None, rotation: list[float]|None=None) -> None:
    '''
    Pose given object

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


def render_scene(scene: Scene|None, write_still: bool=False) -> None:
    '''
    Render scene

    Args
        scene: Scene to render
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
