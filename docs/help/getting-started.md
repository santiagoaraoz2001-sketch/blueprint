# Getting Started with Blueprint

## What is Blueprint?

Blueprint is a local ML experiment workbench built by Specific Labs. It provides a visual pipeline editor for designing, running, and analyzing machine learning experiments. You connect modular blocks into pipelines, configure them, run experiments, and view results — all from a single interface running on your own machine.

Blueprint is designed for ML practitioners who want a lightweight, privacy-respecting tool that keeps data and compute local.

## System Requirements

- **OS:** macOS 12+, Linux (Ubuntu 20.04+, Fedora 36+), or Windows 10+ (WSL2 recommended)
- **Python:** 3.10 or later
- **RAM:** 8 GB minimum, 16 GB recommended for local model inference
- **Disk:** 2 GB free for the application, plus space for models and datasets
- **GPU (optional):** NVIDIA GPU with CUDA 11.7+ for GPU-accelerated blocks, or Apple Silicon with Metal support

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/specific-labs/blueprint.git
cd blueprint
```

### 2. Set up the Python environment

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 4. Start the backend server

```bash
uvicorn backend.main:app --reload --port 8000
```

### 5. Start the frontend dev server

```bash
cd frontend
npm run dev
```

Open your browser to `http://localhost:5173` to access Blueprint.

## Your First Pipeline

Follow these steps to create and run a simple pipeline.

### Step 1: Create a Project

Click **New Project** on the home screen. Give it a name like "My First Experiment" and click **Create**.

### Step 2: Open the Pipeline Editor

You will be taken to the pipeline editor canvas automatically. This is where you design your experiment as a directed graph of blocks.

### Step 3: Add Blocks

Open the block palette on the left sidebar. Drag a **Dataset Loader** block onto the canvas. Then drag a **Train/Test Split** block and a **Model Training** block.

### Step 4: Connect Blocks

Click an output port on the Dataset Loader and drag to the input port on the Train/Test Split block. Connect the split outputs to the Model Training block inputs. Ports are color-coded by data type — matching colors indicate compatible connections.

### Step 5: Configure Blocks

Click on each block to open its configuration panel on the right. Set the dataset path, split ratio, and model parameters as needed.

### Step 6: Validate and Run

Press **Cmd+S** to save your pipeline. Click the **Run** button in the toolbar. Blueprint will validate the pipeline and execute each block in topological order. You can monitor progress in real time via the output panel.

### Step 7: View Results

Once the run completes, switch to the Results view (**Cmd+6**) to see metrics, outputs, and visualizations produced by your pipeline.

## Next Steps

- Read the [Pipeline Editor](pipeline-editor.md) guide to learn canvas features in depth.
- Explore the [Block Reference](blocks.md) to understand available block types.
- Check the [Configuration](configuration.md) guide for project and workspace settings.
- See [Running Pipelines](running-pipelines.md) for monitoring and re-run capabilities.
