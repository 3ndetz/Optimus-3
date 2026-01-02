"""
Docstring for Optimus-3.autoclef_test_optimized

AutoClef - interface between Minecraft and python using Py4J

This script connects AutoClef, Optimus3 VLA together, with simple web visualization. 
"""
import io
import numpy as np
from PIL import Image
import torch
import argparse
import logging
import sys
import threading
import time
import traceback
import copy
from typing import Literal
from py4j.java_gateway import CallbackServerParameters, GatewayParameters, JavaGateway, DEFAULT_PORT
from py4j.java_collections import MapConverter, ListConverter
from http.server import HTTPServer, BaseHTTPRequestHandler
import base64
import json
from urllib.parse import urlparse

# Import the agent (adjust the import if your path is different)
from minecraftoptimus.model.agent.optimus3 import Optimus3Agent


def to_java(obj, gateway):
    if isinstance(obj, dict):
        return MapConverter().convert({k: to_java(v, gateway) for k, v in obj.items()}, gateway._gateway_client)
    elif isinstance(obj, list):
        return ListConverter().convert([to_java(x, gateway) for x in obj], gateway._gateway_client)
    else:
        return obj


def numpy_to_list(d):
    if isinstance(d, np.ndarray):
        return d.tolist()
    elif isinstance(d, dict):
        return {k: numpy_to_list(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [numpy_to_list(x) for x in d]
    else:
        return d


def pilImage_to_b64(img: Image.Image) -> str:
    ret = io.BytesIO()
    fmt = img.format or "PNG"
    img.save(ret, fmt)
    # ret.seek(0)
    return base64.b64encode(ret.getvalue()).decode("ascii")


class WebHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for streaming agent state"""
    app_ref = None
    
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = self.get_html()
            self.wfile.write(html.encode())
        elif self.path == '/api/state':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            state = {
                "screenshot": self.app_ref.last_screenshot_b64 or "",
                "camera": self.app_ref.last_action.get("camera", [0, 0]),
                "buttons": self.app_ref.last_keys,
                "timing": getattr(self.app_ref, 'last_timing', {}),
                "camera_sensitivity": getattr(self.app_ref, 'camera_sensitivity', 1.0),
                "text": self.app_ref.text,
                "task_type": self.app_ref.task_type
            }
            self.wfile.write(json.dumps(state).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/set_task':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode())
                self.app_ref.text = data.get('text', '')
                self.app_ref.task_type = data.get('task_type', 'action')
                # Parse camera_sensitivity as float if present, else default
                cam_sens = data.get('camera_sensitivity', -15.0)
                try:
                    cam_sens = float(cam_sens)
                except Exception:
                    cam_sens = 7.0
                self.app_ref.camera_sensitivity = cam_sens
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"status": "error"}')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress log messages
    
    def get_html(self):
        return """<!DOCTYPE html>
<html>
<head>
    <title>Optimus Agent Monitor</title>
    <style>
        body { font-family: Arial; margin: 20px; background: #1e1e1e; color: #fff; }
        .container { max-width: 1000px; margin: 0 auto; }
        .panel { background: #2d2d2d; padding: 15px; margin: 10px 0; border-radius: 5px; }
        img { max-width: 100%; border-radius: 5px; margin: 10px 0; }
        .camera { font-size: 24px; color: #4fc3f7; font-weight: bold; }
        .keys { display: grid; grid-template-columns: repeat(auto-fit, minmax(80px, 1fr)); gap: 5px; }
        .key { padding: 8px; background: #424242; border-radius: 3px; text-align: center; font-size: 12px; }
        .key.active { background: #4caf50; color: #000; }
        h2 { color: #4fc3f7; border-bottom: 2px solid #4fc3f7; padding-bottom: 10px; }
        .timings { font-size: 16px; margin-top: 10px; }
        .timing-row { display: flex; justify-content: space-between; padding: 2px 0; }
        .timing-label { color: #90caf9; }
        .timing-value { color: #fff; font-weight: bold; }
        .row { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
        select, input[type=text] { font-size: 16px; padding: 4px; border-radius: 3px; border: none; margin-right: 10px; }
        button { font-size: 16px; padding: 4px 12px; border-radius: 3px; border: none; background: #4fc3f7; color: #222; cursor: pointer; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎮 Optimus-3 Agent Monitor</h1>
        <div class="panel">
            <h2>Task Selection</h2>
            <div class="row">
                <input type="text" id="camera_sensitivity" placeholder="7.0" style="width:30px;">
                <input type="text" id="text_input" placeholder="Enter task text..." style="width:300px;">
                <select id="task_type_select">
                    <option value="action">Action</option>
                    <option value="planning">Planning</option>
                    <option value="captioning">Captioning</option>
                    <option value="embodied_qa">Embodied QA</option>
                    <option value="grounding">Grounding</option>
                </select>
                <button onclick="setTask()">Set Task</button>
            </div>
            <div class="row">
                <span>Current text: <span id="current_text"></span></span>
                <span>Current type: <span id="current_task_type"></span></span>
            </div>
        </div>
        <div class="panel">
            <h2>Camera Input (Pitch, Yaw)</h2>
            <div class="camera" id="camera">---, ---</div>
        </div>
        <div class="panel">
            <h2>Game Screenshot (128x128 input)</h2>
            <img id="screenshot" src="" style="border: 2px solid #4fc3f7;">
        </div>
        <div class="panel">
            <h2>Active Keys</h2>
            <div class="keys" id="keys"></div>
        </div>
        <div class="panel">
            <h2>Frame Timings (seconds)</h2>
            <div class="timings" id="timings"></div>
        </div>
    </div>
    <script>
        async function setTask() {
            const text = document.getElementById('text_input').value;
            const task_type = document.getElementById('task_type_select').value;
            const camera_sensitivity = document.getElementById('camera_sensitivity').value;
            await fetch('/api/set_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, task_type, camera_sensitivity })
            });
        }
        const updateInterval = setInterval(async () => {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                // Update camera
                const camera = data.camera;
                document.getElementById('camera').innerText = `Pitch: ${camera[0]?.toFixed(2) || '--'}, Yaw: ${camera[1]?.toFixed(2) || '--'}`;
                // Update screenshot
                if (data.screenshot) {
                    document.getElementById('screenshot').src = 'data:image/png;base64,' + data.screenshot;
                }
                // Update keys
                const keysDiv = document.getElementById('keys');
                keysDiv.innerHTML = '';
                Object.entries(data.buttons || {}).forEach(([key, val]) => {
                    const div = document.createElement('div');
                    div.className = 'key' + (val ? ' active' : '');
                    div.innerText = key;
                    keysDiv.appendChild(div);
                });
                // Update timings
                const timingsDiv = document.getElementById('timings');
                const timings = data.timing || {};
                let html = '';
                for (const [label, value] of Object.entries(timings)) {
                    html += `<div class='timing-row'><span class='timing-label'>${label.replace('_', ' ')}:</span> <span class='timing-value'>${(value).toFixed(3)} sec</span></div>`;
                }
                timingsDiv.innerHTML = html;
                // Update current text/type
                document.getElementById('current_text').innerText = data.text || '';
                document.getElementById('current_task_type').innerText = data.task_type || '';
            } catch (e) { console.error(e); }
        }, 500);
    </script>
</body>
</html>"""


example_imgio = io.BytesIO()
Image.open('debug_game_screenshot.png').convert('RGB').save(example_imgio, format='PNG')

class MineBridgeApp:
    def __init__(self, nickname, server, port=DEFAULT_PORT, web_port=8888):
        self.nickname = nickname
        self.server = server
        self.port = port
        self.web_port = web_port
        self.chat_queue = []
        self.java_gateway = None
        self.main_thread_active = {"active": True}
        # Shared state for web visualization
        self.last_screenshot_b64 = None
        self.last_action = {}
        self.last_keys = {}
        self.camera_sensitivity = 7.0  # Change this to increase/decrease camera speed
        self.last_timing = {}
        # New: text and task_type for agent logic
        self.text = "kill"
        self.task_type = "action"

    def pprint(self, message: str, *args, **kwargs):
        """Prints a message with a prefix containing the nickname and server."""
        print(f"[JavaBridge] {self.nickname}@{self.server} >> {message}", str(*args), str(**kwargs))

    def start_web_server(self):
        """Start minimal web server in background"""
        WebHandler.app_ref = self
        server = HTTPServer(('localhost', self.web_port), WebHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.pprint(f"Web server started at http://localhost:{self.web_port}")

    def mine_bridge_handler(self):
        """Main handler for the py4j bridge."""
        self.start_web_server()
        global model
        last_text = None
        last_task_type = None
        while self.main_thread_active["active"]:
            try:
                self.pprint("Starting Python callback server...")
                _app_ref: "MineBridgeApp" = self

                class PythonCallback(object):
                    def isStarted(self):
                        return True
                    def onUpdateServerInfo(self, *args, **kwargs): pass
                    def onDeath(self, *args, **kwargs): pass
                    def onKill(self, *args, **kwargs): pass
                    def onAutoclefEvent(self, *args, **kwargs): pass
                    def onDamage(self, *args, **kwargs): pass
                    def onDamageConfirmed(self, *args, **kwargs): pass
                    def onCaptchaSolveRequest(self, *args, **kwargs): pass
                    def onVoiceFeed(self, *args, **kwargs): pass
                    def agentCommandRequest(self, *args, **kwargs): return ""
                    def onVerifedChat(self, msgMas=None): return msgMas
                    def onChatMessage(self, msg=""): return msg
                    class Java:
                        implements = ["adris.altoclef.PythonCallback"]

                callback = PythonCallback()
                self.java_gateway = JavaGateway(
                    gateway_parameters=GatewayParameters(port=self.port),
                    callback_server_parameters=CallbackServerParameters(port=self.port + 1),
                    python_server_entry_point=callback,
                    start_callback_server=True,
                )
                mc = self.java_gateway.entry_point

                initial_commands = self.chat_queue.copy()
                self.chat_queue.clear()

                ingame = False
                while not ingame and self.main_thread_active["active"]:
                    try:
                        ingame = mc.handshake()
                    except Exception as e:
                        self.pprint("Waiting for handshake...")
                        ingame = False
                    if not ingame:
                        time.sleep(1)

                for command in initial_commands:
                    mc.RunInnerCommand(command)

                if not self.main_thread_active["active"]:
                    break

                self.pprint("✓ Connected! Minecraft is in-game.")
                # === MAIN AGENT LOOP WITH FPS TIMING ===
                target_frame_time = 0.05  # 20 FPS
                iter = 0
                while self.main_thread_active["active"] and mc.handshake():
                    # Get screenshot
                    # COMMENT OUT BELOW TO USE REAL SCREENSHOT FROM MINECRAFT
                    # imgio = example_imgio
                    # screenshot_bytes = imgio.getvalue()
                    # END COMMENT OUT
                    t0 = time.time()
                    screenshot_bytes = mc.getScreenshot()
                    t1 = time.time()
                    # UNCOMMENT BELOW TO USE REAL SCREENSHOT FROM MINECRAFT
                    if hasattr(screenshot_bytes, 'tostring'):
                        screenshot_bytes = bytes(screenshot_bytes)
                    imgio = io.BytesIO(screenshot_bytes)
                    img = Image.open(imgio).convert('RGB')
                    t2 = time.time()
                    img_128 = img.resize((128, 128))
                    obs = np.array(img_128)
                    self.last_screenshot_b64 = pilImage_to_b64(img_128)  # base64.b64encode(imgio.getvalue()).decode('utf-8')
                    # --- AGENT LOGIC: handle text/task_type changes ---
                    if self.text != last_text or self.task_type != last_task_type:
                        if model is not None and self.task_type in ["action", "planning", "captioning", "embodied_qa", "grounding"]:
                            model.reset(self.text)
                            print(f"✓ Task updated: from [{last_task_type}] {last_text} to [{self.task_type}] {self.text}")
                        last_text = self.text
                        last_task_type = self.task_type
                    t3 = time.time()
                    with torch.no_grad():
                        if self.task_type == "action":
                            raw_action, memory = model.get_action({"image": obs}, self.text)
                            action_dict = copy.deepcopy(dict(numpy_to_list(raw_action)))
                            action = action_dict
                        elif self.task_type == "captioning":
                            # Captioning returns text, not action; just skip action
                            action = {"camera": [0.0, 0.0]}
                        elif self.task_type == "embodied_qa":
                            # Embodied QA returns text, not action; just skip action
                            action = {"camera": [0.0, 0.0]}
                        elif self.task_type == "grounding":
                            # Grounding returns text, not action; just skip action
                            action = {"camera": [0.0, 0.0]}
                        elif self.task_type == "planning":
                            # Planning returns text, not action; just skip action
                            action = {"camera": [0.0, 0.0]}
                        else:
                            action = {"camera": [0.0, 0.0]}
                        # --- Insert logic for attack ---
                        if "attack" in action and action["attack"] > 0:
                            for k in ["jump", "left", "right", "sneak", "sprint"]:
                                action[k] = np.array(0)
                    t4 = time.time()
                    camera = action_dict.get("camera", [0.0, 0.0])
                    if isinstance(camera, np.ndarray):
                        camera = camera.tolist()
                    if not isinstance(camera, list):
                        camera = [float(camera[0]) if hasattr(camera, '__getitem__') else 0.0,
                                 float(camera[1]) if hasattr(camera, '__len__') and len(camera) > 1 else 0.0]
                    camera = [float(c) * self.camera_sensitivity for c in camera[:2]]
                    self.last_action = {
                        "camera": [round(float(c), 2) for c in camera[:2]],
                        "buttons": {k: int(v) for k, v in action_dict.items() if k != "camera"}
                    }
                    self.last_keys = self.last_action["buttons"]
                    action_dict["camera"] = camera
                    t5 = time.time()
                    action_java_map = to_java(numpy_to_list(action_dict), self.java_gateway)
                    mc.executeAgentActions(action_java_map)
                    t6 = time.time()
                    elapsed = t6 - t0
                    sleep_time = max(0, target_frame_time - elapsed)
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    self.last_timing = {
                        "get_screenshot": round((t1-t0), 3) if t1 else None,
                        "decode_image": round((t2-t1), 3) if t1 else None,
                        "resize_numpy": round((t3-t2), 3) if t1 else None,
                        "inference": round((t4-t3), 3) if t1 else None,
                        "prepare_action": round((t5-t4), 3) if t1 else None,
                        "send_action": round((t6-t5), 3) if t1 else None,
                        "total": round((t6-t0), 3)
                    }
                    iter += 1
                    if iter % 60 == 0:
                        actual_fps = 1.0 / (time.time() - t0)
                        self.pprint(f"✓ {iter} frames | FPS: {actual_fps:.1f} | Camera: [{self.last_action['camera'][0]:.1f}, {self.last_action['camera'][1]:.1f}] | Timing: {self.last_timing}")
                        iter = 0
            except KeyboardInterrupt:
                self.pprint("Shutting down...")
                self.main_thread_active["active"] = False
            except Exception as e:
                self.pprint(f"Error: {e}")
                traceback.print_exc()
                time.sleep(2)
            finally:
                if self.java_gateway:
                    self.pprint("Shutting down Java gateway.")
                    self.java_gateway.shutdown()
                    self.java_gateway = None
                break
        self.pprint("Bridge handler finished.")


# ========== AGENT SETUP ==========
USE_AI_AGENT = True

if USE_AI_AGENT:
    model = Optimus3Agent(
        "MinecraftOptimus/Optimus-3-ActionHead",
        "MinecraftOptimus/Optimus-3",
        "MinecraftOptimus/Optimus-3-Task-Router",
        # device="cuda:0"
        device="mps"
    )
else:
    model = None

task = "kill a player"
if model:
    model.reset(task)

if __name__ == "__main__":
    app = MineBridgeApp(nickname="NetTyan", server="localhost", port=DEFAULT_PORT, web_port=8888)
    app.mine_bridge_handler()
