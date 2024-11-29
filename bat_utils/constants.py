from enum import Enum

# -------------------------------
# Constants

DEFAULT_CLASS_NAME = 'Background'
BAT_SCENE_NAME = 'BAT_Scene'
BAT_VIEW_LAYER_NAME = 'BAT_ViewLayer'
BAT_SEGMENTATION_MASK_MAT_NAME = 'BAT_segmentation_mask'
INV_DISTORTION_MAP_NAME = 'DistortionMap'
BAT_MOVIE_CLIP_NAME = 'BAT_MovieClip'
BAT_DISTORTION_NODE_GROUP_NAME = 'BAT_Distort'


# -------------------------------
# Enums

class OutputFormat(str, Enum):
    '''
    String Enum to store image output formats

    Keys
        PNG: PNG file format
        OPEN_EXR: OpenEXR Multilayer format
    '''
    PNG = 'PNG'
    OPEN_EXR = 'OPEN_EXR_MULTILAYER'

class ColorDepth(str, Enum):
    '''
    String Enum to store output color depth

    Keys
        HALF: Half float (16 bits)
        FULL: Full float (32 bits)
    '''
    HALF = '16'
    FULL = '32'
