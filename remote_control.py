import json
import logging
import http.server
import bpy
import threading
import socketserver
import atexit
from bpy.app.handlers import persistent
from bpy.types import Scene, AddonPreferences, Context
from bpy.props import BoolProperty, IntProperty

from . import utils


# -------------------------------
# Preferences

def update_enable_remote_interface(self, context: Context) -> None:
    '''
    Enable/Disable HTTP server

    Args:
        context : Current context
    '''
    if context.preferences.addons[__package__].preferences.http_enable:
        BATRemoteControl.start_server()
    else:
        BATRemoteControl.stop_server()


def update_http_server_port(self, context: Context) -> None:
    '''
    Restart the remote HTTP server with new port

    Args:
        context : Current context
    '''
    BATRemoteControl.restart_server()


class BATRemoteControlPreferences(AddonPreferences):
    ''' Addon Preferences for the HTTP Remote Interface
    '''

    bl_idname = __package__

    http_enable: BoolProperty(
        name="Enable BAT HTTP Remote Interface",
        default=True,
        update = update_http_server_port
    )

    http_port: IntProperty(
        name="BAT HTTP Remote Interface port",
        default=12345,
        min = 1024,
        soft_min = 1024,
        max = 49151,
        soft_max = 49151,
        update = update_http_server_port
    )

    def draw(self, context: Context) -> None:
        '''
        Draw BAT HTTP Remote Interface preferences

        Args:
            context : Current context
        '''
        layout = self.layout
        layout.label(text="BAT HTTP Remote Interface")
        layout.prop(self, "http_enable")
        layout.prop(self, "http_port")


class BATRequestHandler(http.server.BaseHTTPRequestHandler):
    '''HTTP Request Handler for BAT

    Can be used to get/set pose of objects, camera parameters and current frame
    '''
    
    def _send_response(self, message: dict[str, str]) -> None:
        '''Send response json
        '''
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        try:
            self.wfile.write(json.dumps(message).encode('utf-8'))
        except Exception as e:
            self.wfile.write(json.dumps({'status':'failed', 'message':str(e)}).encode('utf-8'))
    

    def do_POST(self) -> None:
        '''Handle POST requests
        '''
        # Parse request data
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = {}
        status = 'failed'
        message = ''

        try:
            data = json.loads(post_data)
        except Exception as e:
            message = str(e)
            data = {}
        
        # Handle camera parameters
        if 'camera' in data:
            cam_data = data['camera']
            scene = bpy.context.scene
            scene.bat_properties.camera.sensor_width = cam_data.get('sensor_width', scene.bat_properties.camera.sensor_width)
            scene.bat_properties.camera.fx = cam_data.get('fx', scene.bat_properties.camera.fx)
            scene.bat_properties.camera.fy = cam_data.get('fy', scene.bat_properties.camera.fy)
            scene.bat_properties.camera.px = cam_data.get('cx', scene.bat_properties.camera.px)
            scene.bat_properties.camera.py = cam_data.get('cy', scene.bat_properties.camera.py)
            scene.bat_properties.camera.p1 = cam_data.get('p1', scene.bat_properties.camera.p1)
            scene.bat_properties.camera.p2 = cam_data.get('p2', scene.bat_properties.camera.p2)
            scene.bat_properties.camera.k1 = cam_data.get('k1', scene.bat_properties.camera.k1)
            scene.bat_properties.camera.k2 = cam_data.get('k2', scene.bat_properties.camera.k2)
            scene.bat_properties.camera.k3 = cam_data.get('k3', scene.bat_properties.camera.k3)
            scene.bat_properties.camera.k4 = cam_data.get('k4', scene.bat_properties.camera.k4)
            scene.bat_properties.camera.upscale_factor = cam_data.get('upscale_factor', scene.bat_properties.camera.upscale_factor)
            bpy.ops.bat.generate_distortion_map()
            status = 'success'
            message += 'Updated camera parameters, '
        
        # Handle object pose
        if 'pose' in data:
            obj_data = data['pose']
            obj_name = obj_data.get('name')
            if obj_name:
                obj = bpy.data.objects.get(obj_name)
                if obj:
                    obj.location = obj_data.get('location', obj.location)
                    obj.rotation_euler = obj_data.get('rotation', obj.rotation_euler)
                    status = 'success'
                    message += f'Updated pose of {obj_name}, '
        
        # Handle frame update
        if 'frame' in data:
            frame = data['frame']
            bpy.context.scene.frame_set(frame)
            status = 'success'
            message += f'Set frame to {frame}, '

        # Handle render request
        if 'render' in data:
            scene = bpy.context.scene
            render_data = data['render']

            render = render_data.get('render', False)
            annotation = render_data.get('annotation', False)
            
            # Deselect all objects
            for object in bpy.data.objects:
                object.select_set(False)
            
            if render:
                utils.render_scene(scene, True)
                status = 'success'
                message += f'Saved rendered frame ({scene.frame_current}) to {scene.render.frame_path(frame=scene.frame_current)}, '

            # if annotation:
            #     utils.setup_bat_scene()
            #     bat_scene = bpy.data.scenes.get(utils.BAT_SCENE_NAME)
            #     bat_scene.bat_properties.save_annotation = True
            #     # Set file name
            #     render_filepath_temp = bat_scene.render.filepath
            #     bat_scene.render.filepath = bat_scene.render.frame_path(frame=bat_scene.frame_current)
                    
            #     # Render image
            #     bpy.ops.render.render(write_still=False, scene=scene.name)

            #     # Reset output path
            #     bat_scene.render.filepath = render_filepath_temp
            #     bat_scene.bat_properties.save_annotation = False
            #     # utils.remove_bat_scene()

            #     status = 'success'
            #     message += f'Saved rendered annotations for frame ({scene.frame_current}) to {scene.render.filepath}, '
            
        # Send response back to client
        if not message:
            message = f"The request doesn't contain any valid keys. Valid keys are 'camera', 'pose', 'frame' and 'render. Got keys: {','.join(list(data.keys()))}"
        response = {'status': status, 'message': message}
        self._send_response(response)


    def do_GET(self) -> None:
        '''Handle GET requests
        '''
        query = self.path.split('?')[0].strip('/')

        response = {'status': 'failed'}

        if query == "object":
            obj_name = self.path.split('?name=')[-1] if '?name=' in self.path else None
            if obj_name:
                obj = bpy.data.objects.get(obj_name)
                if obj:
                    response = {
                        "status": "success",
                        "object": obj_name,
                        "location": list(obj.location),
                        "rotation": list(obj.rotation_euler)
                    }
                else:
                    response = {"status": "failed", "message": f"Object '{obj_name}' not found."}
            else:
                response = {"status": "failed", "message": "Object name not provided."}

        elif query == "frame":
            frame = bpy.context.scene.frame_current
            response = {"status": "success", "frame": frame}
        
        self._send_response(response)
    

class BATRemoteControl:
    server = None

    @classmethod
    def start_server(cls):
        preferences = bpy.context.preferences
        addon_prefs = preferences.addons[__package__].preferences
        if cls.server is None and addon_prefs.http_enable:
            host = '0.0.0.0'
            port = addon_prefs.http_port
            socketserver.TCPServer.allow_reuse_address = True
            cls.server = socketserver.TCPServer((host, port), BATRequestHandler)
            cls.server_thread = threading.Thread(target=cls.server.serve_forever)
            cls.server_thread.daemon = True
            cls.server_thread.start()
            logging.info(f'BAT HTTP server started on http://{host}:{port}')

    @classmethod
    def stop_server(cls):
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()
            cls.server_thread.join()
            cls.server = None
            logging.info('BAT HTTP server stopped.')

    @classmethod
    def restart_server(cls):
        cls.stop_server()
        cls.start_server()


# -------------------------------
# Handlers

def onRegister(scene: Scene) -> None:
    '''
    Setup default class upon registering the addon

    Args:
        scene : Current scene
    '''
    BATRemoteControl.start_server()


@persistent
def onFileLoaded(scene: Scene) -> None:
    '''
    Setup default class upon loading a new Blender file

    Args:
        scene : Current scene 
    '''
    BATRemoteControl.start_server()

@atexit.register
def onBlenderClose() -> None:
    '''
    Handler to stop the server when Blender shuts down
    '''
    BATRemoteControl.stop_server()


# -------------------------------
# Register/Unregister

classes = [
    BATRemoteControlPreferences
    ]

def register() -> None:
    '''
    Start HTTP Server
    '''
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.app.handlers.depsgraph_update_pre.append(onRegister)
    bpy.app.handlers.load_post.append(onFileLoaded)
    BATRemoteControl.start_server()

def unregister() -> None:
    '''
    Stop HTTP Server
    '''
    if onRegister in bpy.app.handlers.depsgraph_update_pre:
        bpy.app.handlers.depsgraph_update_pre.remove(onRegister)
    if onFileLoaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(onFileLoaded)
    BATRemoteControl.stop_server()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()