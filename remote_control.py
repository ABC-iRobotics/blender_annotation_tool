import json
import http.server
import bpy
import threading
import socketserver
import atexit
from bpy.app.handlers import persistent
from bpy.types import Scene

from . import utils

class BATRequestHandler(http.server.BaseHTTPRequestHandler):
    '''HTTP Request Handler for BAT

    Can be used to get/set pose of objects, camera parameters and current frame
    '''
    
    def _send_response(self, message):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(message).encode('utf-8'))
    

    def do_POST(self) -> None:
        '''Handle POST requests
        '''
        # Parse request data
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(post_data)
        
        status = 'failed'
        message = ''
        
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
        response = {'status': status, 'message': message}
        self._send_response(response)


    def do_GET(self) -> None:
        '''Handle GET requests
        '''
        query = self.path.split('?')[0].strip('/')

        response = {'status': 'failed'}

        if query == "object":
            obj_name = self.path.split('?name=')[-1] if '?name=' in self.path else None
            obj = bpy.data.objects.get(obj_name) if obj_name else None
            if obj:
                response = {
                    "status": "success",
                    "object": obj_name,
                    "location": list(obj.location),
                    "rotation": list(obj.rotation_euler)
                }
            else:
                response = {"status": "failed", "message": f"Object '{obj_name}' not found."}

        elif query == "frame":
            frame = bpy.context.scene.frame_current
            response = {"status": "success", "frame": frame}
        
        self._send_response(response)
    

class BATRemoteControl:
    server = None

    @classmethod
    def start_server(cls):
        if cls.server is None:
            host = '0.0.0.0'
            port = 12345
            socketserver.TCPServer.allow_reuse_address = True
            cls.server = socketserver.TCPServer((host, port), BATRequestHandler)
            cls.server_thread = threading.Thread(target=cls.server.serve_forever)
            cls.server_thread.daemon = True
            cls.server_thread.start()
            print(f'BAT HTTP server started on http://{host}:{port}')

    @classmethod
    def stop_server(cls):
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()
            cls.server_thread.join()
            cls.server = None
            print('BAT HTTP server stopped.')


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

def register() -> None:
    '''
    Start HTTP Server
    '''
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


if __name__ == "__main__":
    register()