import os
import bpy
import json
import numbers
import numpy as np
from bpy.types import Scene
from . import constants
from json.decoder import JSONDecodeError

def setup_camera(cam_data: dict[str, float|int]) -> None:
    '''
    Setup BAT camera, given a dict containing camera data

    Args
        cam_data: dict containing camera data
    '''
    scene = bpy.context.scene
    scene.bat_properties.camera.sensor_width = cam_data.get('sensor_width', scene.bat_properties.camera.sensor_width)
    scene.bat_properties.camera.fx = cam_data.get('fx', scene.bat_properties.camera.fx)
    scene.bat_properties.camera.fy = cam_data.get('fy', scene.bat_properties.camera.fy)
    scene.bat_properties.camera.cx = cam_data.get('cx', scene.bat_properties.camera.cx)
    scene.bat_properties.camera.cy = cam_data.get('cy', scene.bat_properties.camera.cy)
    scene.bat_properties.camera.p1 = cam_data.get('p1', scene.bat_properties.camera.p1)
    scene.bat_properties.camera.p2 = cam_data.get('p2', scene.bat_properties.camera.p2)
    scene.bat_properties.camera.k1 = cam_data.get('k1', scene.bat_properties.camera.k1)
    scene.bat_properties.camera.k2 = cam_data.get('k2', scene.bat_properties.camera.k2)
    scene.bat_properties.camera.k3 = cam_data.get('k3', scene.bat_properties.camera.k3)
    scene.bat_properties.camera.k4 = cam_data.get('k4', scene.bat_properties.camera.k4)


def distort(vec: np.array, intr: np.array, distortion_params:np.array) -> tuple[np.array,np.array]:
    '''
    Get distorted image coordinates from undistorted coordinates

    Args
        vec: NumPy array containing undistorted image coordinates. Should be of shape (2,w*h),
            where "w" is the width and "h" is the height of the image. The first element along the first dimesion
            should hold the y coordinates (along height) and the second element of the first dimension should contain
            the x coordinates (along width). The [0,0] point should be upper left corner (so the first element of both
            the y and the x coordinates should be 0)
        intr: NumPy array containing camera intrinsics (fx,fy,cx,cy)
        distortion_params: NumPy array containing lens distortion parameters (p1,p2,k1,k2,k3,k4)

    Returns:
        Distorted image coordinates corresponding to the coordinates in "vec". It is a tuple of the x and y coordinates
    '''
    # Unpack values from inputs
    y,x = vec
    fx,fy,cx,cy = intr
    p1,p2,k1,k2,k3,k4 = distortion_params

    # Normalize image coordinates
    x = (x-cx)/fx
    y = (y-cy)/fy

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
    image_x = fx * xd + cx
    image_y = fy * yd + cy
    return (image_x,image_y)


def interpolate(x: np.ndarray, mask: np.ndarray, flip: int, falloff: int = 1) -> np.ndarray:
    '''
    Interpolate missing values in x following a meandering pattern

    Args
        x: 2D NumPy array with missing/incorrect values (shape: (W,H), dtype: int or float)
        mask: 2D NumPy array telling which values of x to use for interpolation (shape: (W,H) must match with x.shape, dtype: bool)
            "True" elements signal that the corresponding values in x should be kept
        flip: Decides the direction of the meandering pattern (1=forward, 0=backward)
        falloff: Decides how much proximity influences interpolation (1=linear, 2=quadratic, ...)
    
    Returns
        The array with missing values filled. If a value cannot be determined (at the beginning and end of meander) it will be np.nan
    '''
    # Make a copy of the arrays that can be modified
    x_copy = np.copy(x)
    mask_copy = np.copy(mask)

    # Flip every second row starting from "flip", so the arrays can be flattened in a meander pattern
    x_copy[flip::2, :] = x_copy[flip::2, ::-1]
    mask_copy[flip::2, :] = mask_copy[flip::2, ::-1]

    # Flatten the arrays
    x_copy = x_copy.flatten()
    mask_copy = mask_copy.flatten()

    # Get indices where the mask is "True" and create an array containing all possible indices (xs)
    ind = np.where(mask_copy)[0]
    xs = np.arange(x_copy.size)

    # Get interpolated values at "xs", given the values in the flattened array (x_copy) at "ind"
    # Make values that could not be interpolated np.nan and reshape the resulted array
    inter = np.reshape(np.interp(xs,ind,x_copy[ind], left=np.nan, right=np.nan), x.shape)

    # Get closest left and right elements of "ind" for each element in xs
    l = np.insert(ind,ind.size,ind[-1])[np.searchsorted(ind,xs,side='left')]
    r = np.insert(ind,0,ind[0])[np.searchsorted(ind,xs,side='right')]

    # Calculate minimum distance of elements in "xs" from elements in "ind"
    # Use 1/(dist+1) to create weights
    # Reshape the resulted array and apply falloff
    weights = np.power(np.reshape(1/(np.min(np.stack((np.abs(xs-l),np.abs(xs-r))),axis=0)+1),x.shape), falloff)
    
    # Flip every second row starting from "flip", so the array elements correspond to elements in "x"
    inter[flip::2, :] = inter[flip::2, ::-1]
    weights[flip::2, :] = weights[flip::2, ::-1]

    return inter, weights


def fill_missing_values(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    '''
    Fill missing elements in x by applying the meandering interpolation in all four directions

    Args
        x: 2D NumPy array with missing/incorrect values (shape: (W,H), dtype: int or float)
        mask: 2D NumPy array telling which values of x to use for interpolation (shape: (W,H) must match with x.shape, dtype: bool)
            "True" elements signal that the corresponding values in x should be kept
    
    Returns
        The array with missing values filled.
    '''
    # Apply the meandering interpolation forward and backward, going row-by-row
    i1,w1 = interpolate(x,mask,0)
    i2,w2 = interpolate(x,mask,1)

    # Apply the meandering interpolation forward and backward, going column-by-column
    i3,w3 = interpolate(x.T,mask.T,0)
    i4,w4 = interpolate(x.T,mask.T,1)

    # Transpose the results so the align with i1,i2, and w1,w2
    i3 = i3.T
    w3 = w3.T
    i4 = i4.T
    w4 = w4.T

    # Stack all interpolated values and associated weights
    inter = np.stack((i1,i2,i3,i4),axis=-1)
    weights = np.stack((w1,w2,w3,w4), axis=-1)

    # Return weighted average, ignoring np.nan values
    return np.nansum(inter*weights, axis=-1)/np.nansum(weights, axis=-1)


def generate_inverse_distortion_map(width: int, height: int, intr: np.array, distortion_params: np.array) -> np.array:
    '''
    Generates an inverse distortion map for fast image distortion lookup

    Args
        width: Width of the image
        height: Height of the image
        intr: NumPy array containing camera intrinsics (fx,fy,cx,cy)
        distortion_params: NumPy array containing lens distortion parameters (p1,p2,k1,k2,k3,k4)
    
    Returns
        NumPy array containing the inverse distorion map. The shape is (height,width,3)
            The last dimension is for the y and x coordinates and a flag that signals if the pixel comes from projection (or is interpolated)
    '''
    # Create empty inverse distortion map
    inv_distortion_map = np.zeros((height,width,2))
    changed_items = np.zeros((height,width,1))

    # Create image coordinates matrix
    coords = np.moveaxis(np.mgrid[0:height,0:width],[0],[2])

    # Get distorted coordinates
    distorted_xs, distorted_ys = distort(np.reshape(np.moveaxis(coords, [2],[0]), (2,height*width)), intr, distortion_params)

    A = np.reshape(distorted_xs, (height,width))
    diffs = np.roll(A, -1, axis=1)[:, :-1] - A[:, :-1]
    mask_x = np.append(diffs > 0, (diffs > 0)[:, -1][:, None], axis=1)
    mask_x = np.reshape(mask_x, (height*width))

    A = np.reshape(distorted_ys, (height,width))
    A = A.T
    diffs = np.roll(A, -1, axis=1)[:, :-1] - A[:, :-1]
    mask_y = np.append(diffs > 0, (diffs > 0)[:, -1][:, None], axis=1)
    mask_y = mask_y.T
    mask_y = np.reshape(mask_y, (height*width))

    # Filter distorted an undistorted coordinates (only leave te ones that are inside the image after distortion)
    valid_indices = np.logical_and(np.logical_and(distorted_xs>=0,distorted_xs<width),np.logical_and(distorted_ys>=0,distorted_ys<height))
    valid_indices = np.logical_and(valid_indices, mask_x)
    valid_indices = np.logical_and(valid_indices, mask_y)
    distorted_xs = distorted_xs[valid_indices].astype(int)
    distorted_ys = distorted_ys[valid_indices].astype(int)
    coords = np.reshape(coords, (height*width, 2))[valid_indices]

    inv_distortion_map[distorted_ys,distorted_xs] = coords
    changed_items[distorted_ys,distorted_xs] = 1
    inv_distortion_map[:,:,0] = fill_missing_values(inv_distortion_map[:,:,0],changed_items.astype(bool)[:,:,0])
    inv_distortion_map[:,:,1] = fill_missing_values(inv_distortion_map[:,:,1],changed_items.astype(bool)[:,:,0])
    inv_distortion_map = np.append(inv_distortion_map, changed_items, axis=2)
    return inv_distortion_map


def setup_bat_distortion(scene: Scene) -> set[str]:
    '''
    Setup the compositor with the correct distortion node and generate DistortionMap

    Args
        scene: Scene to apply the distortion to (not the BAT scene)

    Returns
        Execution status
    '''

    # Get image parameters
    cam = scene.bat_properties.camera
    width = int(scene.render.resolution_x * (scene.render.resolution_percentage/100))
    height = int(scene.render.resolution_y * (scene.render.resolution_percentage/100))

    # Set Blender camera focal length
    blender_camera = bpy.data.cameras[scene.camera.data.name]
    blender_camera.type = 'PERSP'
    blender_camera.lens_unit = 'MILLIMETERS'
    blender_camera.lens = (cam.fx/scene.render.resolution_x)*cam.sensor_width

    # Get camera parameters
    intr = [cam.fx,cam.fy,cam.cx,cam.cy]
    distort = [cam.p1,cam.p2,cam.k1,cam.k2,cam.k3,cam.k4]

    # Generate distorion map
    distortion_map = generate_inverse_distortion_map(width, height, intr, distort)
    distortion_map = np.append(distortion_map, np.ones((height,width,1)), axis=2)  # Add alpha channel

    # Save distortion map as image
    if not constants.INV_DISTORTION_MAP_NAME in bpy.data.images:
        dist_map_img = bpy.data.images.new(constants.INV_DISTORTION_MAP_NAME, width, height, alpha=True, float_buffer=True, is_data=True)
    else:
        dist_map_img = bpy.data.images[constants.INV_DISTORTION_MAP_NAME]
        if dist_map_img.size[0] != width or dist_map_img.size[1] != height:
            bpy.data.images.remove(dist_map_img, do_unlink=True)
            dist_map_img = bpy.data.images.new(constants.INV_DISTORTION_MAP_NAME, width, height, alpha=True, float_buffer=True, is_data=True)
    dist_map_img.pixels = distortion_map.flatten()

    # Create clip image
    clip_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'clip.png')
    clip_img = bpy.data.images.new('BAT_clip', width, height, alpha=False, float_buffer=True, is_data=True)
    clip_img.pixels = np.zeros((height,width,4)).flatten()
    clip_img.filepath_raw = clip_image_path
    clip_img.save()
    bpy.data.images.remove(clip_img, do_unlink=True)

    # Create a movieclip for using camera lens distortion from compositor
    mov_clip = bpy.data.movieclips.get(constants.BAT_MOVIE_CLIP_NAME)
    if not mov_clip is None:
        bpy.data.movieclips.remove(mov_clip, do_unlink=True)
    mov_clip = bpy.data.movieclips.load(clip_image_path)
    mov_clip.name = constants.BAT_MOVIE_CLIP_NAME
    mov_clip.tracking.camera.distortion_model = 'BROWN'
    mov_clip.tracking.camera.sensor_width = scene.bat_properties.camera.sensor_width
    fx = scene.bat_properties.camera.fx
    fy = scene.bat_properties.camera.fy if scene.bat_properties.camera.fy > 0 else 0.00001
    mov_clip.tracking.camera.pixel_aspect = max(fx/fy,0.1)
    mov_clip.tracking.camera.focal_length = (fx/scene.render.resolution_x)*scene.bat_properties.camera.sensor_width
    mov_clip.tracking.camera.units = 'MILLIMETERS'
    mov_clip.tracking.camera.principal_point[0] = (scene.bat_properties.camera.cx/(width/2))-1
    mov_clip.tracking.camera.principal_point[1] = (scene.bat_properties.camera.cy/(height/2))-1
    mov_clip.tracking.camera.brown_p1 = scene.bat_properties.camera.p1
    mov_clip.tracking.camera.brown_p2 = scene.bat_properties.camera.p2
    mov_clip.tracking.camera.brown_k1 = scene.bat_properties.camera.k1
    mov_clip.tracking.camera.brown_k2 = scene.bat_properties.camera.k2
    mov_clip.tracking.camera.brown_k3 = scene.bat_properties.camera.k3
    mov_clip.tracking.camera.brown_k4 = scene.bat_properties.camera.k4

    # Create new node group for compositor
    bat_distort_group = bpy.data.node_groups.get(constants.BAT_DISTORTION_NODE_GROUP_NAME)
    if bat_distort_group is None:
        bat_distort_group = bpy.data.node_groups.new(constants.BAT_DISTORTION_NODE_GROUP_NAME, 'CompositorNodeTree')
        if not hasattr(bat_distort_group, 'inputs'):
            # Blender 4.0 +
            bat_distort_group.interface.new_socket('Image', in_out='INPUT', socket_type='NodeSocketColor')
        if not hasattr(bat_distort_group, 'outputs'):
            # Blender 4.0 +
            bat_distort_group.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')

        # Create group inputs
        group_inputs = bat_distort_group.nodes.get('NodeGroupInput')
        if group_inputs is None:
            group_inputs = bat_distort_group.nodes.new('NodeGroupInput')

        # create group outputs
        group_outputs = bat_distort_group.nodes.get('NodeGroupOutput')
        if group_outputs is None:
            group_outputs = bat_distort_group.nodes.new('NodeGroupOutput')

        movie_distortion_node = bat_distort_group.nodes.new('CompositorNodeMovieDistortion')
        movie_distortion_node.clip = bpy.data.movieclips[constants.BAT_MOVIE_CLIP_NAME]
        movie_distortion_node.distortion_type = 'DISTORT'

        bat_distort_group.links.new(group_inputs.outputs['Image'], movie_distortion_node.inputs['Image'])
        bat_distort_group.links.new(movie_distortion_node.outputs['Image'], group_outputs.inputs['Image'])
    else:
        # Re-select the movie clip because we re-create it every time we generate
        movie_distortion_node = bat_distort_group.nodes.get('Movie Distortion')
        movie_distortion_node.clip = bpy.data.movieclips[constants.BAT_MOVIE_CLIP_NAME]


    # Add to compositor if compositor workspace is empty
    if scene.node_tree is None:
        scene.use_nodes = True
        for n in scene.node_tree.nodes:
            scene.node_tree.nodes.remove(n)
        render_layers_node = scene.node_tree.nodes.new('CompositorNodeRLayers')
        render_layers_node.scene = scene
        bat_distortion_node = scene.node_tree.nodes.new('CompositorNodeGroup')
        bat_distortion_node.node_tree = bpy.data.node_groups[constants.BAT_DISTORTION_NODE_GROUP_NAME]
        compositor_node = scene.node_tree.nodes.new('CompositorNodeComposite')

        scene.node_tree.links.new(render_layers_node.outputs['Image'], bat_distortion_node.inputs['Image'])
        scene.node_tree.links.new(bat_distortion_node.outputs['Image'], compositor_node.inputs['Image'])
        

    return {'FINISHED'}


def distort_image(image_name: str) -> tuple[set[str],str]:
    '''
    Distort given image using the BAT Distortion Node

    Args
        image_name: The name of the image data in Blender

    Returns
        Execution status and message
    '''
    message = ''

    # Read distortion map
    dist_map_img = bpy.data.images.get(constants.INV_DISTORTION_MAP_NAME)
    if not dist_map_img is None:
        w, h = dist_map_img.size
        dmap = np.array(dist_map_img.pixels[:], dtype=np.float32)
        dmap = np.reshape(dmap, (h, w, 4))[:,:,:]
        ys = dmap[:,:,0].flatten().astype(int)
        xs = dmap[:,:,1].flatten().astype(int)

        # Read image to be distorted
        img = bpy.data.images.get(image_name)
        if not img is None:
            if w == img.size[0] and h == img.size[1]:
                img = np.array(img.pixels[:], dtype=np.float32)
                img = np.reshape(img, (h, w, 4))[:,:,:]
                img = img[:,:,0:4]

                # Distort image
                dimg = np.reshape(img[ys,xs],(h,w,4))

                # Save it in an image
                if not 'Distorted Image' in bpy.data.images:
                    dist_img = bpy.data.images.new('Distorted Image', w, h, alpha=True, float_buffer=True, is_data=True)
                else:
                    dist_img = bpy.data.images['Distorted Image']
                    if dist_img.size[0] != w or dist_img.size[1] != h:
                        bpy.data.images.remove(dist_img, do_unlink=True)
                        dist_img = bpy.data.images.new('Distorted Image', w, h, alpha=True, float_buffer=True, is_data=True)
                dist_img.pixels = dimg.flatten()
            else:
                message = 'DistortionMap and image sizes do not match! Have you updated the DistortionMap and re-rendered the scene with the new resolution?'
                return ({'CANCELLED'}, message)

    return ({'FINISHED'}, message)


def import_camera_data(scene: Scene) -> tuple[set[str],str]:
    '''
    Import camera data from JSON file

    Args
        scene: Scene in which to import the camera data into (not the BAT scene)
    '''
    message = ''
    # Read json file
    filepath = os.path.abspath(scene.bat_properties.camera.calibration_file)
    if os.path.isfile(filepath):
        with open(filepath,'r') as f:
            try:
                calib_data = json.loads(f.read())
            except JSONDecodeError:
                message = 'The selected file is not a valid JSON!'
                return ({'CANCELLED'}, message)
        if isinstance(calib_data, dict):
            if 'cam_mtx' in calib_data:
                if isinstance(calib_data['cam_mtx'], list):
                    cam_mtx = calib_data['cam_mtx']
                    if len(cam_mtx) == 3 and all((isinstance(e, list) for e in cam_mtx)):
                        if all((len(e)==3 for e in cam_mtx)) and all((all(isinstance(ie,numbers.Number) for ie in e) for e in cam_mtx)):
                            scene.bat_properties.camera.fx = cam_mtx[0][0]
                            scene.bat_properties.camera.fy = cam_mtx[1][1]
                            scene.bat_properties.camera.cx = cam_mtx[0][2]
                            scene.bat_properties.camera.cy = cam_mtx[1][2]
                        else:
                            message = '"cam_mtx" must be 3x3 matrix!'
                            return ({'CANCELLED'}, message)
                    else:
                        message = '"cam_mtx" must be 3x3 matrix!'
                        return ({'CANCELLED'}, message)
                else:
                    message = '"cam_mtx" field must be a list!'
                    return ({'CANCELLED'}, message)
            if 'dist' in calib_data:
                if isinstance(calib_data['dist'], list):
                    dist = calib_data['dist']
                    if len(dist) == 6 and all(isinstance(e,numbers.Number) for e in dist):
                        scene.bat_properties.camera.k1 = dist[0]
                        scene.bat_properties.camera.k2 = dist[1]
                        scene.bat_properties.camera.p1 = dist[2]
                        scene.bat_properties.camera.p2 = dist[3]
                        scene.bat_properties.camera.k3 = dist[4]
                        scene.bat_properties.camera.k4 = dist[5]
                    else:
                        message = '"dist" field must be a list of six numbers! (k1,k2,p1,p2,k3,k4)'
                        return ({'CANCELLED'}, message)
                else:
                    message = '"dist" field must be a list!'
                    return ({'CANCELLED'}, message)
        else:
            message = 'The file must contain a dictionary!'
            return ({'CANCELLED'}, message)
    else:
        message = 'Could not access the selected file!'
        return ({'CANCELLED'}, message)

    return ({'FINISHED'}, message)