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
                "camera_sensitivity": getattr(self.app_ref, 'camera_sensitivity', 1.0)
            }
            self.wfile.write(json.dumps(state).encode())
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
    </style>
</head>
<body>
    <div class="container">
        <h1>🎮 Optimus-3 Agent Monitor</h1>
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
            } catch (e) { console.error(e); }
        }, 500);
    </script>
</body>
</html>"""


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

        # Camera sensitivity multiplier
        self.camera_sensitivity = 5.0  # Change this to increase/decrease camera speed
        self.last_timing = {}

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
        
        while self.main_thread_active["active"]:
            try:
                self.pprint("Starting Python callback server...")
                _app_ref: "MineBridgeApp" = self

                class PythonCallback(object):
                    def isStarted(self):
                        return True

                    def onUpdateServerInfo(self, *args, **kwargs):
                        pass

                    def onDeath(self, *args, **kwargs):
                        pass

                    def onKill(self, *args, **kwargs):
                        pass

                    def onAutoclefEvent(self, *args, **kwargs):
                        pass

                    def onDamage(self, *args, **kwargs):
                        pass

                    def onDamageConfirmed(self, *args, **kwargs):
                        pass

                    def onCaptchaSolveRequest(self, *args, **kwargs):
                        pass

                    def onVoiceFeed(self, *args, **kwargs):
                        pass

                    def agentCommandRequest(self, *args, **kwargs):
                        return ""

                    def onVerifedChat(self, msgMas=None):
                        if msgMas:
                            msg_text = msgMas.get("msg", "")
                            user = msgMas.get("user", "unknown")
                            # _app_ref.pprint errored, when run from js process spawn

                            # _app_ref.pprint(f"[MC CHAT] {user}: {msg_text}")
                        return msgMas

                    def onChatMessage(self, msg=""):
                        # _app_ref.pprint(f"[MC CHAT RAW] {msg}")
                        return msg

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
                    t0 = time.time()
                    # Get screenshot
                    t1 = None
                    screenshot_bytes = mc.getScreenshot()
                    t1 = time.time()
                    if hasattr(screenshot_bytes, 'tostring'):
                        screenshot_bytes = bytes(screenshot_bytes)
                    imgio = io.BytesIO(screenshot_bytes)
                    img = Image.open(imgio).convert('RGB')
                    t2 = time.time()
                    img_128 = img.resize((128, 128))
                    obs = np.array(img_128)
                    # Store screenshot for web (raw 128x128 PNG)
                    self.last_screenshot_b64 = base64.b64encode(imgio.getvalue()).decode('utf-8')
                    # Run inference
                    t3 = time.time()
                    with torch.no_grad():
                        action, memory = model.get_action({"image": obs}, task)
                    t4 = time.time()
                    # Extract action dict - camera is ALREADY CONTINUOUS [-10, 10]
                    action_dict = copy.deepcopy(dict(numpy_to_list(action)))
                    # Get camera values (already in final form)
                    camera = action_dict.get("camera", [0.0, 0.0])
                    if isinstance(camera, np.ndarray):
                        camera = camera.tolist()
                    if not isinstance(camera, list):
                        camera = [float(camera[0]) if hasattr(camera, '__getitem__') else 0.0,
                                 float(camera[1]) if hasattr(camera, '__len__') and len(camera) > 1 else 0.0]
                    # Apply camera sensitivity multiplier
                    camera = [float(c) * self.camera_sensitivity for c in camera[:2]]
                    # Store last action for web display
                    self.last_action = {
                        "camera": [round(float(c), 2) for c in camera[:2]],
                        "buttons": {k: int(v) for k, v in action_dict.items() if k != "camera"}
                    }
                    self.last_keys = self.last_action["buttons"]
                    # Send to Minecraft
                    # Overwrite camera in action_dict for actual execution
                    action_dict["camera"] = camera
                    t5 = time.time()
                    action_java_map = to_java(action_dict, self.java_gateway)
                    mc.executeAgentActions(action_java_map)
                    t6 = time.time()
                    # FPS CONTROL: Calculate sleep time
                    elapsed = t6 - t0
                    sleep_time = max(0, target_frame_time - elapsed)
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    # Timing breakdown for web
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
        device="cuda:0"
    )
else:
    model = None

task = "kill a player"
if model:
    model.reset(task)

if __name__ == "__main__":
    app = MineBridgeApp(nickname="NetTyan", server="localhost", port=DEFAULT_PORT, web_port=8888)
    app.mine_bridge_handler()
