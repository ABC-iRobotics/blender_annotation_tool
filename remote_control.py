import json
import time
import logging
import http.server
from typing import Callable
import bpy
import threading
import queue
import socketserver
import atexit
from bpy.app.handlers import persistent
from bpy.types import Scene, AddonPreferences, Context
from bpy.props import BoolProperty, IntProperty
from typing import Any

from . import utils

# -------------------------------
# Timer for executing non thread-safe blender API calls in the main thread


TIMER_FREQUENCY = 1.0  # Re-run timer every second
REQUEST_TIMEOUT = 10  # Timeout seconds for handling GET requests


execution_queue = queue.Queue()  # Queue to hold functions for execution in Blender's main thread
result_queue = queue.Queue()  # Queue to hold function results


def run_in_main_thread(function: Callable[[],Any]) -> None:
    '''Function to enqueue tasks for main thread execution

    Args
        function: Function to be executed
    '''
    execution_queue.put(function)


def execute_queued_functions() -> float:
    '''Timer function to execute queued tasks in Blender's main thread

    Returns
        The number of seconds after which the function will be executed again
    '''
    while not execution_queue.empty():
        function = execution_queue.get()
        try:
            logging.info(f"Executing function {function}")
            function()
        except Exception as e:
            logging.error(f"Error executing function {function} in main thread: {e}")
    return TIMER_FREQUENCY  # Run the function again after TIMER_FREQUENCY seconds


def register_timer_function() -> None:
    '''Register the timer function in Blender
    '''
    if not bpy.app.timers.is_registered(execute_queued_functions):
        bpy.app.timers.register(execute_queued_functions)
        logging.info('Registered queue executor')


def unregister_timer_function() -> None:
    '''Unregister the timer function in Blender
    '''
    if bpy.app.timers.is_registered(execute_queued_functions):
        bpy.app.timers.unregister(execute_queued_functions)
        logging.info('Unregistered queue executor')


# -------------------------------
# Preferences

def update_enable_remote_interface(self, context: Context) -> None:
    '''
    Enable/Disable HTTP server

    Args:
        context : Current context
    '''
    if context.preferences.addons[__package__].preferences.http_enable:
        register_timer_function()
        BATRemoteControl.start_server()
    else:
        BATRemoteControl.stop_server()
        unregister_timer_function()


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
        update = update_enable_remote_interface
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


# -------------------------------
# Helper functions

def get_object_pose(object_name: str|None) -> None:
    '''Get pose of a given object

    Args
        object_name: Name of the object
    '''
    pose = {}
    obj = bpy.data.objects.get(object_name)
    if obj:
        pose['location'] = list(obj.location)
        pose['rotation'] = list(obj.rotation_euler)
    result_queue.put(pose)


def get_frame_num() -> None:
    '''Get frame number
    '''
    result_queue.put(bpy.context.scene.frame_current)


# -------------------------------
# HTTP Interface

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
            # Invalid JSON
            message = str(e)
            data = {}
        
        # Handle camera parameters
        if 'camera' in data:
            cam_data = data['camera']
            run_in_main_thread(lambda: utils.setup_camera(cam_data))
            run_in_main_thread(bpy.ops.bat.generate_distortion_map)
            status = 'success'
            message += 'Updated camera parameters, '
        
        # Handle object pose
        if 'pose' in data:
            obj_data = data['pose']
            obj_name = obj_data.get('name')
            if obj_name:
                run_in_main_thread(lambda: utils.set_object_pose(obj_name, obj_data.get('location'), obj_data.get('rotation')))
                status = 'success'
                message += f'Updated pose of {obj_name}, '
        
        # Handle frame update
        if 'frame' in data:
            frame = data['frame']
            run_in_main_thread(lambda: bpy.context.scene.frame_set(frame))
            status = 'success'
            message += f'Set frame to {frame}, '

        # Handle render request
        if 'render' in data:
            render_data = data['render']

            render = render_data.get('render', False)
            annotation = render_data.get('annotation', False)
            
            if render:
                run_in_main_thread(lambda: utils.render_scene(None, True)) 
                status = 'success'
                message += f'Rendered frame, '

            if annotation:
                run_in_main_thread(utils.bat_render_annotation)
                status = 'success'
                message += f'Saved rendered annotations, '
            
        # Send response back to client
        if not message:
            message = f"The request doesn't contain any valid keys. Valid keys are 'camera', 'pose', 'frame' and 'render. Got keys: {','.join(list(data.keys()))}"
        response = {'status': status, 'message': message}
        self._send_response(response)


    def do_GET(self) -> None:
        '''Handle GET requests
        '''
        # Parse query
        query = self.path.split('?')[0].strip('/')

        response = {'status': 'failed'}

        # Handle request for object pose
        if query == "object":
            obj_name = self.path.split('?name=')[-1] if '?name=' in self.path else None
            if obj_name:
                run_in_main_thread(lambda: get_object_pose(obj_name))
                start_time = time.time()
                while result_queue.empty():
                    if time.time() - start_time > REQUEST_TIMEOUT:
                        self.send_error(500, "Timeout waiting for Blender response")
                        return
                
                # Retrieve the response from the result queue
                response_content = result_queue.get()
                if response_content:
                    response = {
                        "status": "success",
                        "object": obj_name,
                        "location": response_content['location'],
                        "rotation": response_content['rotation']
                    }
                else:
                    response = {"status": "failed", "message": f"Object '{obj_name}' not found."}
            else:
                response = {"status": "failed", "message": "Object name not provided."}

        # Handle request for frame number
        elif query == "frame":
            run_in_main_thread(get_frame_num)
            start_time = time.time()
            while result_queue.empty():
                if time.time() - start_time > REQUEST_TIMEOUT:
                    self.send_error(500, "Timeout waiting for Blender response")
                    return
                
            # Retrieve the response from the result queue
            response_content = result_queue.get()
            response = {"status": "success", "frame": response_content}
        
        self._send_response(response)
    

class BATRemoteControl:
    '''Class for BAT HTTP Interface
    '''
    server = None

    @classmethod
    def start_server(cls):
        '''Start the HTTP server
        '''
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
            logging.info(f'BAT HTTP server started at http://{host}:{port}')

    @classmethod
    def stop_server(cls):
        '''Stop the HTTP server
        '''
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()
            cls.server_thread.join()
            cls.server = None
            logging.info('BAT HTTP server stopped.')

    @classmethod
    def restart_server(cls):
        '''Restart the HTTP server
        '''
        cls.stop_server()
        cls.start_server()


# -------------------------------
# Handlers

def onRegister(scene: Scene) -> None:
    '''
    Setup HTTP server and timer when registering addon

    Args:
        scene : Current scene
    '''
    register_timer_function()
    BATRemoteControl.start_server()


@persistent
def onFileLoaded(scene: Scene) -> None:
    '''
    Setup default class upon loading a new Blender file

    Args:
        scene : Current scene 
    '''
    register_timer_function()
    BATRemoteControl.start_server()


@atexit.register
def onBlenderClose() -> None:
    '''
    Handler to stop the server when Blender shuts down
    '''
    BATRemoteControl.stop_server()
    unregister_timer_function()


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
    register_timer_function()
    bpy.app.handlers.depsgraph_update_pre.append(onRegister)
    bpy.app.handlers.load_post.append(onFileLoaded)
    BATRemoteControl.start_server()


def unregister() -> None:
    '''
    Stop HTTP Server
    '''
    unregister_timer_function()
    if onRegister in bpy.app.handlers.depsgraph_update_pre:
        bpy.app.handlers.depsgraph_update_pre.remove(onRegister)
    if onFileLoaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(onFileLoaded)
    BATRemoteControl.stop_server()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()