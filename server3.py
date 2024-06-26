import asyncio
import websockets
import threading
import bge
import socket
import json
import math
import mathutils    

clients = set()
selected_object = None
reported_errors = set()  # To keep track of reported errors
mouse_visible = True


def truncate(value, digits=3):
    if isinstance(value, float):
        return round(value, digits)
    elif isinstance(value, (list, mathutils.Vector, mathutils.Euler)):
        return [truncate(v, digits) for v in value]
    return value

async def broadcast_data():
    while True:
        if clients:
            scene = bge.logic.getCurrentScene()
            objects = [{"name": obj.name} for obj in scene.objects]
            object_list_message = json.dumps({"type": "objects", "data": objects})
            
            # Broadcast object list
            await asyncio.gather(*[client.send(object_list_message) for client in clients])
            
            # Broadcast selected object properties if one is selected
            if selected_object:
                obj = scene.objects.get(selected_object)
                if obj:
                    properties = {
                        "position": list(obj.worldPosition),
                        "rotation": list(obj.worldOrientation.to_euler()),
                        "scale": list(obj.worldScale),
                        "mass": obj.mass,
                        "linearVelocity": list(obj.linearVelocity),
                        "angularVelocity": list(obj.angularVelocity)
                    }
                    for key in obj.getPropertyNames():
                        properties[key] = obj[key]
                    properties_message = json.dumps({"type": "object_properties", "data": properties})
                    await asyncio.gather(*[client.send(properties_message) for client in clients])
        
        await asyncio.sleep(0.5)  # Update twice per second

async def handle_client(websocket, path):
    global selected_object
    clients.add(websocket)
    try:
        async for message in websocket:
            data = json.loads(message)
            if data['type'] == 'get_objects':
                await send_objects(websocket)
            elif data['type'] == 'get_object_properties':
                selected_object = data['name']
                await send_object_properties(websocket, data['name'])
            elif data['type'] == 'update_object_property':
                await update_object_property(websocket, data)
            elif data['type'] == 'toggle_visibility':
                await toggle_object_visibility(websocket, data['object'])
            elif data['type'] == 'get_game_info':
                await send_game_info(websocket)
            elif data['type'] == 'set_game_speed':
                await set_game_speed(websocket, data['speed'])
            elif data['type'] == 'toggle_physics_debug':
                await toggle_physics_debug(websocket)
            elif data['type'] == 'toggle_mouse':
                await toggle_mouse(websocket)
            elif data['type'] == 'restart_game':
                await restart_game(websocket)
            elif data['type'] == 'end_game':
                await end_game(websocket)
    except websockets.exceptions.ConnectionClosedError:
        print("Client connection closed")
    finally:
        clients.remove(websocket)


async def toggle_object_visibility(websocket, object_name):
    scene = bge.logic.getCurrentScene()
    obj = scene.objects.get(object_name)
    if obj:
        obj.visible = not obj.visible
        await websocket.send(json.dumps({"type": "visibility_updated", "object": object_name, "visible": obj.visible}))
    else:
        await websocket.send(json.dumps({"type": "error", "message": f"Object '{object_name}' not found"}))

# async def send_game_info(websocket):
#     info = {
#         "fps": bge.logic.getAverageFrameRate(),
#         "game_speed": bge.logic.getTimeScale(),
#         "physics_debug": bge.logic.getCurrentScene().debugDraw,
#         "mouse_visible": bge.logic.getCurrentScene().mouseCursor,
#     }
#     await websocket.send(json.dumps({"type": "game_info", "data": info}))

async def set_game_speed(websocket, speed):
    bge.logic.setTimeScale(float(speed))
    await websocket.send(json.dumps({"type": "game_speed_updated", "speed": speed}))

async def send_game_info(websocket):
    global mouse_visible
    info = {
        "fps": bge.logic.getAverageFrameRate(),
        "game_speed": bge.logic.getTimeScale(),
        "mouse_visible": mouse_visible
    }
    await websocket.send(json.dumps({"type": "game_info", "data": info}))

async def toggle_mouse(websocket):
    global mouse_visible
    mouse_visible = not mouse_visible
    bge.render.showMouse(mouse_visible)
    await websocket.send(json.dumps({"type": "mouse_visibility_updated", "visible": mouse_visible}))

async def toggle_physics_debug(websocket):
    # UPBGE doesn't have a built-in physics debug visualization
    # You might need to implement your own visualization method
    # For now, we'll just send a message that this feature is not available
    await websocket.send(json.dumps({"type": "error", "message": "Physics debug visualization is not available in this version of UPBGE"}))

# async def toggle_mouse(websocket):
#     scene = bge.logic.getCurrentScene()
#     default_object = scene.objects['__default__']
#     default_object.visible = not default_object.visible
#     bge.render.showMouse(default_object.visible)
#     await websocket.send(json.dumps({"type": "mouse_visibility_updated", "visible": default_object.visible}))

async def restart_game(websocket):
    bge.logic.restartGame()
    await websocket.send(json.dumps({"type": "game_restarted"}))

async def end_game(websocket):
    bge.logic.endGame()
    await websocket.send(json.dumps({"type": "game_ended"}))
async def send_objects(websocket):
    scene = bge.logic.getCurrentScene()
    objects = [{"name": obj.name} for obj in scene.objects]
    await websocket.send(json.dumps({"type": "objects", "data": objects}))

async def send_object_properties(websocket, object_name):
    scene = bge.logic.getCurrentScene()
    obj = scene.objects.get(object_name)
    if obj:
        try:
            properties = {
                "basic": {
                    "position": {
                        "x": truncate(obj.worldPosition.x),
                        "y": truncate(obj.worldPosition.y),
                        "z": truncate(obj.worldPosition.z)
                    },
                    "rotation": {
                        "x": truncate(math.degrees(obj.worldOrientation.to_euler().x)),
                        "y": truncate(math.degrees(obj.worldOrientation.to_euler().y)),
                        "z": truncate(math.degrees(obj.worldOrientation.to_euler().z))
                    },
                    "scale": {
                        "x": truncate(obj.worldScale.x),
                        "y": truncate(obj.worldScale.y),
                        "z": truncate(obj.worldScale.z)
                    }
                },
                "physics": {"status": "Not applicable"},
                "game": {},
                "materials": []
            }
            
            # Physics properties (only if the object has physics)
            if obj.getPhysicsId():
                if hasattr(obj, 'mass') and hasattr(obj, 'linearVelocity') and hasattr(obj, 'angularVelocity'):
                    properties["physics"] = {
                        "mass": truncate(obj.mass),
                        "linearVelocity": {
                            "x": truncate(obj.linearVelocity.x),
                            "y": truncate(obj.linearVelocity.y),
                            "z": truncate(obj.linearVelocity.z)
                        },
                        "angularVelocity": {
                            "x": truncate(obj.angularVelocity.x),
                            "y": truncate(obj.angularVelocity.y),
                            "z": truncate(obj.angularVelocity.z)
                        }
                    }
            
            # Game properties
            for key in obj.getPropertyNames():
                value = obj[key]
                if isinstance(value, (int, float, bool, str)):
                    properties["game"][key] = truncate(value)
                elif isinstance(value, (mathutils.Vector, mathutils.Euler)):
                    properties["game"][key] = {
                        "x": truncate(value.x),
                        "y": truncate(value.y),
                        "z": truncate(value.z)
                    }
            
            # Materials (if the object has a mesh)
            if hasattr(obj, 'meshes') and obj.meshes:
                properties["materials"] = [mat.name for mat in obj.meshes[0].materials]
            else:
                properties["materials"] = ["Not applicable"]
            
            await websocket.send(json.dumps({"type": "object_properties", "data": properties}))
        except Exception as e:
            error_msg = f"Error processing object {object_name}: {str(e)}"
            print(error_msg)
            await websocket.send(json.dumps({"type": "error", "message": error_msg}))
    else:
        await websocket.send(json.dumps({"type": "error", "message": f"Object '{object_name}' not found"})) 

async def update_object_property(websocket, data):
    scene = bge.logic.getCurrentScene()
    obj = scene.objects.get(data['object'])
    if obj:
        try:
            property_name = data['property']
            new_value = data['value']
            
            if property_name == 'position':
                axis = data.get('axis', 'x')
                current_position = obj.worldPosition
                setattr(current_position, axis, float(new_value))
                obj.worldPosition = current_position
            elif property_name == 'rotation':
                axis = data.get('axis', 'x')
                current_rotation = obj.worldOrientation.to_euler()
                index = 'xyz'.index(axis)
                current_rotation[index] = math.radians(float(new_value))
                obj.worldOrientation = current_rotation.to_matrix()
            elif property_name == 'scale':
                axis = data.get('axis', 'x')
                current_scale = obj.worldScale
                setattr(current_scale, axis, float(new_value))
                obj.worldScale = current_scale
            else:
                if isinstance(obj[property_name], (int, float)):
                    new_value = float(new_value)
                elif isinstance(obj[property_name], bool):
                    new_value = new_value.lower() in ('true', '1', 'yes')
                obj[property_name] = new_value
            
            await websocket.send(json.dumps({"type": "update_success"}))
        except Exception as e:
            await websocket.send(json.dumps({"type": "error", "message": str(e)}))
    else:
        await websocket.send(json.dumps({"type": "error", "message": f"Object '{data['object']}' not found"}))

async def broadcast_data():
    while True:
        if clients:
            scene = bge.logic.getCurrentScene()
            objects = [{"name": obj.name} for obj in scene.objects]
            object_list_message = json.dumps({"type": "objects", "data": objects})
            
            # Broadcast object list
            await asyncio.gather(*[client.send(object_list_message) for client in clients])
            
            # Broadcast selected object properties if one is selected
            if selected_object:
                await asyncio.gather(*[send_object_properties(client, selected_object) for client in clients])
        
        await asyncio.sleep(0.5)  # Update twice per second

def find_free_port(start_port=8765, max_port=8865):
    for port in range(start_port, max_port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('', port))
            s.close()
            return port
        except OSError:
            continue
    return None

def run_server():
    async def server():
        global websocket_server
        port = find_free_port()
        if port is None:
            print("No free ports found. Unable to start WebSocket server.")
            return

        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                websocket_server = await websockets.serve(handle_client, "localhost", port)
                print(f"WebSocket server started on ws://localhost:{port}")
                await broadcast_data()  # This will run indefinitely
                break  # If successful, exit the loop
            except OSError as e:
                if e.errno == 10048 and attempt < max_attempts - 1:
                    print(f"Port {port} is in use, trying another port...")
                    port = find_free_port(start_port=port+1)
                    if port is None:
                        print("No more free ports found. Unable to start WebSocket server.")
                        return
                else:
                    print(f"Error starting WebSocket server: {e}")
                    return
            except Exception as e:
                print(f"Unexpected error starting WebSocket server: {e}")
                return

    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    try:
        new_loop.run_until_complete(server())
    except Exception as e:
        print(f"Error in run_server: {e}")

# Start the WebSocket server in a separate thread
if not hasattr(bge.logic, 'server_thread'):
    bge.logic.server_thread = threading.Thread(target=run_server)
    bge.logic.server_thread.daemon = True
    bge.logic.server_thread.start()

def update():
    # This function will be called every frame
    # You can add any per-frame logic here if needed
    pass

# This will be called every time the Python controller is triggered
update()