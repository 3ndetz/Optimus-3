import numpy as np
from PIL import Image
import torch
# This sets the default device for all new tensors to MPS
device = "mps"
# torch.set_default_device(device)
# + in env
# Import the agent (adjust the import if your path is different)
from minecraftoptimus.model.agent.optimus3 import Optimus3Agent

# 1. Load your image (replace 'your_image.png' with your screenshot path)
img = Image.open('2025-01-24_04.48.53.png').convert('RGB')
img = img.resize((128, 128))  # Resize if required by the model
obs = np.array(img)
# obs = obs[None, ...]  # Add batch dimension

# 2. Instantiate the model (adjust model paths as needed)
model = Optimus3Agent(
    "MinecraftOptimus/Optimus-3-ActionHead",
    "MinecraftOptimus/Optimus-3",
    "MinecraftOptimus/Optimus-3-Task-Router",
    device=device  # "cpu" or "cuda:0" if you have a GPU
)

# 3. Run inference
task = "kill a player"
model.reset(task)

import json
def numpy_to_list(d):
    if isinstance(d, np.ndarray):
        return d.tolist()
    elif isinstance(d, dict):
        return {k: numpy_to_list(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [numpy_to_list(x) for x in d]
    else:
        return d

for i in range(10):
    with torch.no_grad():
        action, memory = model.get_action({"image": obs}, task)
    print(f"\n--- Run {i+1} ---")
    print("Memory (str):", str(memory))
    print("Memory (tensor):", json.dumps(numpy_to_list(memory), indent=2))
    print("Action buttons:", json.dumps(numpy_to_list(action), indent=2))