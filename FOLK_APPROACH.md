Searched codebase for "make some research in the OPTIMUS INTERNAL codebase (not my tests or mocks!):
1. trace the agent camera control, what values goes to camera movement (delta) of agent?
2. Trace the update time of agent. How often (per second) agent updates its action? Trace through the optimus code", 19 results

Searched codebase for "camera movement, camera delta, action output, get_action, camera, agent, Optimus3Agent", 21 results

Searched for text `camera` (`**/src/minecraftoptimus/model/agent/optimus3.py`), no results

Searched for regex `FPS|update|sleep|time|rate` (`**/src/minecraftoptimus/model/agent/optimus3.py`), 20 results

Searched for text `camera` (`**/src/minecraftoptimus/model/optimus3/optimus3_policy.py`), 2 results

Searched for text `camera` (`**/src/minecraftoptimus/model/steve1/agent.py`), no results

Searched for text `camera` (`**/src/minecraftoptimus/model/steve1/VPT/agent.py`), 13 results

Searched for regex `FPS|update|sleep|time|rate` (`**/src/minecraftoptimus/model/optimus3/optimus3_policy.py`), 4 results

Searched for regex `FPS|update|sleep|time|rate` (`**/src/minecraftoptimus/model/steve1/VPT/agent.py`), 2 results

Searched for text `FPS` (`**/src/minecraftoptimus/model/steve1/agent.py`), 1 result

Read [](file:///c%3A/Repos/experimenting/optimegatron/Optimus-3/src/minecraftoptimus/model/agent/optimus3.py#120-120), lines 120 to 180

Read [](file:///c%3A/Repos/experimenting/optimegatron/Optimus-3/src/minecraftoptimus/model/steve1/agent.py#1-1), lines 1 to 61

Read [](file:///c%3A/Repos/experimenting/optimegatron/Optimus-3/src/minecraftoptimus/model/steve1/agent.py#180-180), lines 180 to 240

Read [](file:///c%3A/Repos/experimenting/optimegatron/Optimus-3/src/minecraftoptimus/model/steve1/agent.py#240-240), lines 240 to 300

Read [](file:///c%3A/Repos/experimenting/optimegatron/Optimus-3/src/minecraftoptimus/model/steve1/MineRLConditionalAgent.py#1-1), lines 1 to 61

Read [](file:///c%3A/Repos/experimenting/optimegatron/Optimus-3/src/minecraftoptimus/model/steve1/VPT/agent.py#120-120), lines 120 to 180

Read [](file:///c%3A/Repos/experimenting/optimegatron/Optimus-3/src/minecraftoptimus/model/steve1/VPT/agent.py#180-180), lines 180 to 239

Read [](file:///c%3A/Repos/experimenting/optimegatron/Optimus-3/src/minecraftoptimus/model/steve1/VPT/lib/actions.py#100-100), lines 100 to 160

Read [](file:///c%3A/Repos/experimenting/optimegatron/Optimus-3/src/minecraftoptimus/model/steve1/VPT/lib/actions.py#160-160), lines 160 to 177

Read [](file:///c%3A/Repos/experimenting/optimegatron/Optimus-3/src/minecraftoptimus/model/steve1/VPT/lib/actions.py#1-1), lines 1 to 61

Read [](file:///c%3A/Repos/experimenting/optimegatron/Optimus-3/src/minecraftoptimus/model/steve1/VPT/lib/actions.py#61-61), lines 61 to 121

Here are the results of tracing the Optimus agent's internal codebase for your questions:

---

### 1. Trace the agent camera control: what values go to camera movement (delta) of agent?

- The camera movement (delta) is ultimately output as the `"camera"` field in the action dictionary.
- In the core agent pipeline, the action is produced by the policy and then post-processed:
  - The policy outputs a (possibly discretized) camera value, which is then converted back to a continuous value using the `ActionTransformer` and its `undiscretize_camera()` method.
- The relevant code is in src/minecraftoptimus/model/steve1/VPT/lib/actions.py:
  - The `CameraQuantizer` class handles discretization and undiscretization of camera values.
  - The camera values are clipped to a range (default: $[-10, 10]$), possibly quantized (linear or mu-law), and then output as a 2D vector (pitch, yaw).
  - The final output to the environment is a continuous 2D numpy array, e.g., `[-10.0, 10.0]`, representing pitch and yaw deltas in degrees per action step.

**Summary:**  
The agent's camera control is a 2D vector (pitch, yaw delta), typically in the range $[-10, 10]$ per step, output as the `"camera"` field in the action dictionary. This is produced by the policy and post-processed by the `ActionTransformer`'s `undiscretize_camera()`.

---

### 2. Trace the update time of agent: how often (per second) does the agent update its action?

- In src/minecraftoptimus/model/steve1/agent.py, the constant `FPS = 20` is defined.
- This is a convention for the agent's intended action rate: **20 actions per second**.
- The actual update rate in a running environment depends on the environment's step loop, but the agent is designed to be called at 20Hz.
- There is no explicit sleep or timing in the agent code itself; the environment or runner is expected to call the agent at this rate.

**Summary:**  
The agent is designed to update its action at 20Hz (20 times per second), as indicated by the `FPS = 20` constant. The actual rate depends on the environment's step loop.

---

**Key references:**
- Camera control: CameraQuantizer and ActionTransformer
- Update rate: FPS = 20

If you need a deeper trace into the policy or want to see the exact data flow for a specific model, let me know!