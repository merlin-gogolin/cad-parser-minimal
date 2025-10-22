<p align="center">
  <img src="assets/env_logo.svg" alt="nuCAD Logo" height="128"/>
  <h1 align="center">nuCAD</h1>
  <h3 align="center" style="font-weight:normal; color:gray;">An open source Gym-style simulator for CAD</h3>
  <p align="center">
    <a href="docs/_build/html/index.html"><img src="https://img.shields.io/badge/Documentation-📖-blue.svg" alt="Documentation"></a>
    <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
    <a href="https://www.opencascade.com/"><img src="https://img.shields.io/badge/Powered%20by-OpenCASCADE-green.svg" alt="Powered by OpenCASCADE"></a>
  </p>
</p>

---

**nuCAD** is a modular, high-performance, and research-friendly RL environment for Computer-Aided Design (CAD). It provides a Gym-like API for programmatic CAD modeling, enabling advanced reinforcement learning, automation, and procedural geometry workflows.

> **"Design, automate, and learn CAD with the power of RL!"**

---

## 🚀 Features
- **Gym-like API for CAD:** Step, reset, and reward structure for RL agents
- **Parallel Environment Support:** Efficient multi-environment training and data collection
- **Robust State Management:** Clean, modular state handling for reproducibility and debugging
- **OpenCASCADE Geometry Engine:** Industrial-grade solid modeling
- **Action Handlers:** Modular, extensible action system for sketches, solids, booleans, and more
- **Visualization & Export:** On-demand 3D rendering and STL/STEP export for downstream use
- **Comprehensive Test Suite:** Integration, unit, and RL-specific tests for reliability

---

## 💡 Why nuCAD?
- **Research-Ready:** Designed for RL, automation, and procedural geometry research
- **Modular & Maintainable:** Clean separation of actions, state, and geometry
- **Scalable:** Parallel environment support for fast data collection
- **Extensible:** Add new actions, handlers, or geometry types easily

---

## 📦 Codebase Structure

```text
nuCAD/
├── env/
│   ├── base_env.py         # Core environment logic
│   ├── rl_env.py           # RL-optimized wrappers (parallel, memory, etc.)
│   ├── action_handlers/    # Modular action handler logic
│   ├── geometry/           # Geometry and sketch operations
│   ├── renderer.py         # Visualization and rendering
│   └── actions.py          # Action definitions (AddSketch, Extrude, etc.)
├── assets/
│   ├── demo.gif            # Demo animation (see above!)
│   ├── logo.png/svg        # Branding assets
├── tests/
│   ├── integration/        # End-to-end and workflow tests
│   ├── rl_env/             # RL environment and parallelism tests
│   ├── unit/               # Unit tests for core logic
│   └── user/               # User-facing and template tests
├── examples/               # Example scripts and workflows
├── scripts/                # Utility and automation scripts
└── ...
```

---

## ⚡ Quickstart

1. **Install dependencies** (see `requirements.txt`)
2. **Run an example:**
   ```python
   from nuCAD.env.rl_env import create_training_env
   from nuCAD.env.actions import AddSketch, AddLine, CloseProfile, MakeFace, Extrude

   env = create_training_env()
   env.reset()
   env.step(AddSketch(origin=(0,0,0), normal=(0,0,1)))
   env.step(AddLine(start=(0,0), end=(1,0)))
   env.step(AddLine(start=(1,0), end=(1,1)))
   env.step(AddLine(start=(1,1), end=(0,1)))
   env.step(AddLine(start=(0,1), end=(0,0)))
   env.step(CloseProfile())
   env.step(MakeFace())
   env.step(Extrude(height=1.0, faces=["f0"]))
   env.export(type="stl", filename="box")
   ```
3. **Explore the tests and examples** for more advanced workflows!

<p align="center"> <img src="assets/agent_logo.svg" alt="nuCAD Agent" width="220"/> </p>

---

## 📄 License
This project is licensed under the MIT License.

---

## 🙏 Acknowledgements
- Built on top of [OpenCASCADE](https://www.opencascade.com/) for robust geometry
- Uses [pythonOCC](https://github.com/tpaviot/pythonocc-core) for Python bindings to OpenCASCADE
- Inspired by OpenAI Gym and modern RL research

---

<p align="center"><b>nuCAD</b> — <i>Design, Automate, and Learn CAD with RL!</i></p>
