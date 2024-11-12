# Blender Annotation Tool (BAT)

A blender addon for 3D scene annotation.

## Installation

The addon requires Blender version 3.1.2 (It might work with a newer Blender version as well)

To install the add-on, download the repository as a zip file. Then, in Blender, navigate to Edit>Preferences> Addons and click Install.
Select the downloaded zip. The addon should then appear in the list of addons (in the Render category). Click the checkbox to activate the addon.

**IMPORTANT: Upon installation, after the addon is activated, click inside the 3D viewport to trigger an update. This sets a default value for the list of classes. Otherwise, the addon will still be functional, but the 'Background' class will be missing, which might be confusing.**

After installation, the addon can be used in the Layout tab's N menu.
![BAT Panel](imgs/bat_panel.png?raw=true "BAT Panel")

## Usage

Use the panel to add, delete, and edit classes. You can select which class you want to configure using the current class dropdown selector. All configured classes will be represented in the annotations. Choosing a mask color is only necessary for visualization purposes (the saved file will have class and instance ID channels included). The `Instance segmentation` checkbox can be used to distinguish between instances of this class. The `Depth map`, `Surface normal`, and `Optical flow` checkboxes can be used to generate the corresponding modalities along with the annotations (these checkboxes are shared across all classes).

If `Save annotations` is checked, the annotations will be saved in a file whenever they are rendered. If `Export class info` is checked, a JSON object containing the mapping between class IDs and class names will be saved upon rendering.

The **render annotation** button allows you to manually render the annotations for the current scene and frame.

The annotations are saved as OpenEXR Multilayer files in a newly created folder called `annotations` in the same directory as the renders. You can use the `OpenEXRReader` class in [this repository](https://github.com/karolyartur/exr_reader) to read these files into Python efficiently.

### Simple usage example with binary segmentation

![Binary segmentation Example](imgs/binary_segmentation.gif)

### Instance segmentation and additional modalities

![Instance Segmentation and other modalities](imgs/instance_segmentation_example.gif)

## HTTP Remote Interface

The HTTP Remote Interface allows remote control of object poses, camera settings, current frame, and rendering through HTTP requests. It starts an HTTP server within Blender, enabling it to accept commands via POST requests for setting parameters and GET requests for retrieving scene data.

### Usage

To use the HTTP Interface, start Blender with BAT enabled. The HTTP server will automatically start using PORT 12345 and listening to remote connections. Below are examples of how to interact with it using `curl`.

**Set the pose of the Cube object when the HTTP Interface is running on localhost**
```bash
curl --header "Content-Type: application/json" \
     --request POST \
     --data '{"pose":{"name":"Cube","location":[1,0,0],"rotation":[0,0,1.5708]}}' \
     http://localhost:12345
```

**Set camera p1 and p2 parameters when the HTTP Interface is running on localhost**
```bash
curl --header "Content-Type: application/json" \
     --request POST \
     --data '{"camera":{"p1":0.5,"p2":0.2}}' \
     http://localhost:12345
```

The available camera settings are:
 - **sensor_width, fx, fy, cx, cy, p1, p2, k1, k2, k3, k4 (all as floats)**
 - **upscale_factor (integer)**
   

**Set the current frame to 1 when the HTTP Interface is running on localhost**
```bash
curl --header "Content-Type: application/json" \
     --request POST \
     --data '{"frame":1}' \
     http://localhost:12345
```

**Trigger a render when the HTTP Interface is running on localhost**
```bash
curl --header "Content-Type: application/json" \
     --request POST \
     --data '{"render":{"render":true}}' \
     http://localhost:12345
```

Multiple settings can be combined in a single request. The order of their execution will be "camera" > "pose" > "frame" > "render":
```bash
curl --header "Content-Type: application/json" \
     --request POST \
     --data '{"camera":{"p1":0.5,"p2":0.2}, "frame":1, "render":{"render":true}}' \
     http://localhost:12345
```

**Get the Current Frame**

Retrieve the current frame of the Blender scene:
```bash
curl http://localhost:12345/frame
```

**Get Object Pose**

Retrieve the current pose (location and rotation) of a specific object:
```bash
curl http://localhost:12345/object?name=Cube
```

Example response:
```json
{
  "status": "success",
  "object": "Cube",
  "location": [1.0, 0.0, 0.0],
  "rotation": [0.0, 0.0, 1.5708]
}
```