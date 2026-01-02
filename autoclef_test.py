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

# Import the agent (adjust the import if your path is different)
from minecraftoptimus.model.agent.optimus3 import Optimus3Agent

import json


def to_java(obj, gateway):
    if isinstance(obj, dict):
        # Рекурсивно конвертируем значения
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

# Optimus-3\src\minecraftoptimus\model\steve1\VPT\agent.py
# AGENT_RESOLUTION = (128, 128)
# AGENT_FPS = 20

# camera
# Optimus-3\src\minecraftoptimus\model\steve1\VPT\lib\actions.py
# The CameraQuantizer class handles discretization and undiscretization of camera values.
# The agent's camera control is a 2D vector (pitch, yaw delta), typically in the range 
# [−10,10] per step, output as the "camera" field in the action dictionary. This is produced by the policy and post-processed by the ActionTransformer's undiscretize_camera().

# 1. Load your image (replace 'your_image.png' with your screenshot path)
img = Image.open('2025-01-24_04.48.53.png').convert('RGB')
img = img.resize((128, 128))  # Resize if required by the model
obs = np.array(img)
# obs = obs[None, ...]  # Add batch dimension


action_response_example = {
    "attack": 0,
    "back": 0,
    "forward": 0,
    "jump": 0,
    "left": 0,
    "right": 0,
    "sneak": 0,
    "sprint": 1,
    "use": 0,
    "drop": 0,
    "inventory": 0,
    "hotbar.1": 0,
    "hotbar.2": 0,
    "hotbar.3": 0,
    "hotbar.4": 0,
    "hotbar.5": 0,
    "hotbar.6": 0,
    "hotbar.7": 0,
    "hotbar.8": 0,
    "hotbar.9": 0,
    "camera": [
        10.0,
        10.0
    ],
    "ESC": 0
}
# looks like Camera
# [0] -10.00000000 (double) to 10.00000000 (double)
# [1] -10.00000000 (double) to 10.00000000 (double) 


class AgentDummy():

    def reset(self, task):
        pass

    # get_action({"image": obs}, task)
    def get_action(self, input, task):
        action = action_response_example
        memory = None  # Placeholder for memory
        return action, memory


USE_AI_AGENT = True

# 2. Instantiate the model (adjust model paths as needed)

if USE_AI_AGENT:
    model = Optimus3Agent(
        "MinecraftOptimus/Optimus-3-ActionHead",
        "MinecraftOptimus/Optimus-3",
        "MinecraftOptimus/Optimus-3-Task-Router",
        device="cuda:0"  # "cpu" or "cuda:0" if you have a GPU
    )
else:
    model = AgentDummy()

# 3. Run inference
task = "kill a player"
model.reset(task)


class MineBridgeApp:
    def __init__(self, nickname, server, port=DEFAULT_PORT):
        self.nickname = nickname
        self.server = server
        self.port = port
        self.chat_queue = []
        self.java_gateway = None
        self.main_thread_active = {"active": True}

    def pprint(self, message: str, *args, **kwargs):
        """Prints a message with a prefix containing the nickname and server."""
        print(f"[JavaBridge] {self.nickname}@{self.server} >> {message}", str(*args), str(**kwargs))

    def check_msg(self, msg: str) -> str:
        """

        """
        if not msg:
            return ""
        return ""

    def mine_bridge_handler(self):
        """
        Main handler for the py4j bridge.
        """
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
                        result = _app_ref.check_msg(msg)
                        if result:
                            _app_ref.BotState = result
                        return msg

                    class Java:
                        implements = ["adris.altoclef.PythonCallback"]

                callback = PythonCallback()
                self.java_gateway = JavaGateway(
                    gateway_parameters=GatewayParameters(
                        port=self.port
                    ),
                    callback_server_parameters=CallbackServerParameters(
                        port=self.port + 1,
                    ),
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
                        self.pprint("TEST EXCEPTION" + str(e))
                        traceback.print_exc()
                        ingame = False
                    if not ingame:
                        self.pprint("Waiting for Minecraft to be in-game...")
                        time.sleep(5)

                for command in initial_commands:
                    mc.RunInnerCommand(command)
                    self.pprint("RUN INNER COMMAND")

                if not self.main_thread_active["active"]:
                    break

                self.pprint("Connection successful! Minecraft is in-game.")

                # chat_thread = threading.Thread(
                #     target=self.chat_queue_handler, args=(mc,)
                # )
                # chat_thread.daemon = True
                # chat_thread.start()
                iter = 0
                while self.main_thread_active["active"] and mc.handshake():
                    # not faster than 20 FPS!
                    time.sleep(0.05)
                    # 0.05s * 20 f/s = 1f
                    # TODO calculate delta time for more accurate fps control
                    # do not need to sleep if processing takes longer than 0.05s
                    # this should be delta from last frame
                    
                    screenshot_bytes = mc.getScreenshot()  # This is a Java byte[] via py4j
                    if hasattr(screenshot_bytes, 'tostring'):
                        # py4j sometimes returns a Java array, convert to bytes
                        screenshot_bytes = bytes(screenshot_bytes)

                    # Open as PIL image
                    img = Image.open(io.BytesIO(screenshot_bytes)).convert('RGB')
                    img = img.resize((128, 128))  # Resize if required by the model
                    # img.save("debug_game_screenshot.png")
                    # Convert to numpy array
                    obs = np.array(img)  # shape (128, 128, 3)
                    with torch.no_grad():
                        action, memory = model.get_action({"image": obs}, task)
                        iter += 1
                        if iter % 60 == 0:
                            self.pprint(f"Iteration {iter}, ")
                            try:
                                # reflection expects Image.Image or image url link
                                # self.pprint("model.reflection(task, obs)", str(model.reflection(task, img)))
                                # semi-full load (240-270w), ~110s
# [JavaBridge] NetTyan@localhost >> model.reflection(task, obs) The image is a screenshot from the game Minecraft, showing the player's first-person view while standing in or near a dirt block with a green leafy block (possibly a bush or tree) partially visible at the bottom center. The player's health bar is partially depleted, with only one out of two hearts remaining. The hotbar contains several items, including a stone pickaxe, a stack of dirt blocks, and some other blocks. The player is currently holding a stone pickaxe in their hand. The environment appears to be outdoors, likely within or on the edge of a dirt slope or hill, as indicated by the block textures and the presence of leaves and dirt. The chat displays the message ""理解和�}> Minecraft gameplay interface, with the player's health and hunger bars visible and both fully filled


                                # self.pprint("model.plan(task)", str(model.plan(task)))
                                # too long 60s + full load + hallucionating

# [JavaBridge] NetTyan@localhost >> model.grounding(task, obs) <think>
# The image shows a Minecraft scene set in a grassy plains biome during daytime. In the foreground, there is a cow standing on the grass to the left. The player's viewpoint is from the first-person perspective, with their right hand visible. The player’s inventory bar at the bottom of the screen is completely empty, indicating no items are currently held. The health bar shows 10 hearts, and the hunger bar is also full. There are no visible structures, mobs, or items in the immediate area. The environment features green grass, scattered flowers, and some distant trees. No other entities or objects are visible in the scene.
# </think>
# <answer>[{"bbox_2d": [350, 25, 429, 311], "label": "pig"}]</answer> 
                                # expects same as reflection
                                # takes 70+ secs, 273w load
                                # self.pprint("model.grounding(task, obs)", str(model.grounding(task, img)))
                            except Exception as e:
                                self.pprint(f"Error printing debug info: {e}")
                                traceback.print_exc()
                            iter = 0

                        action_dict = copy.deepcopy(dict(numpy_to_list(action)))
                        action_java_map = to_java(action_dict, self.java_gateway)
                        mc.executeAgentActions(action_java_map)
                        # self.pprint("Sent actions to Minecraft: " + json.dumps(action_dict))  # , indent=2))
            except KeyboardInterrupt:
                self.pprint("Shutting down...")
                self.main_thread_active["active"] = False
            except Exception as e:
                self.pprint(f"An error occurred: {e}")
                time.sleep(5)
            finally:
                if self.java_gateway:
                    self.pprint("Shutting down Java gateway.")
                    self.java_gateway.shutdown()
                    self.java_gateway = None
                # Break the loop as we want to exit after one attempt for CLI
                break
        self.pprint("Bridge handler finished.")

if __name__ == "__main__":
    app = MineBridgeApp(nickname="NetTyan", server="localhost", port=DEFAULT_PORT)
    app.mine_bridge_handler()

# for i in range(10):
#     with torch.no_grad():
#         action, memory = model.get_action({"image": obs}, task)
#     print(f"\n--- Run {i+1} ---")
#     print("Memory (str):", str(memory))
#     print("Memory (tensor):", json.dumps(numpy_to_list(memory), indent=2))
#     print("Action buttons:", json.dumps(numpy_to_list(action), indent=2))