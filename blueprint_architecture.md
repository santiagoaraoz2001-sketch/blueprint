# Blueprint Developer Architecture & Syntax

This document is designed to be fed directly into an LLM (like Claude or GPT-4) when you want to write custom Modules, Blocks, or Workflows for the Blueprint app.

## Project Structure

```
blueprint/
├── launch.sh               # One-command launcher
├── backend/                # FastAPI backend
│   ├── main.py             # Application entry point
│   ├── config.py           # Paths & feature flags
│   ├── models/             # SQLAlchemy models
│   ├── routers/            # API route handlers
│   ├── engine/             # Pipeline execution engine (executor.py)
│   ├── block_sdk/          # BlockContext — load_input, save_output, log_metric
│   ├── services/           # Business logic & LLM block generation
│   ├── connectors/         # HuggingFace, Jupyter, W&B integrations
│   ├── plugins/            # Plugin system
│   └── alembic/            # Database migrations
├── frontend/               # React + Vite frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── views/          # Page views
│   │   ├── stores/         # Zustand state stores
│   │   └── lib/            # Block registry, design tokens, utilities
│   └── electron/           # Electron main process
├── blocks/                 # Built-in ML block implementations (block.yaml + run.py each)
│   ├── agents/             # Multi-agent, chain-of-thought, orchestrator
│   ├── data/               # Loaders, splitters, augmentation, builders
│   ├── endpoints/          # API publish, HF Hub push, webhooks
│   ├── evaluation/         # LM-Eval Harness, MMLU, bias/fairness
│   ├── flow/               # Gates, branching, loops, parallel execution
│   ├── inference/          # LLM inference, RAG, embeddings
│   ├── merge/              # SLERP, TIES, DARE, Mergekit
│   ├── output/             # Export, reports, model cards
│   └── training/           # LoRA, QLoRA, DPO, full fine-tuning, RLHF
├── scripts/                # Dev tooling (registry gen, scaffolding, audits)
├── extensions/             # Chrome extension for HuggingFace import
└── docs/                   # REPO_FACTS.json, cookbooks, port naming
```

- **Frontend**: React, TypeScript, Vite, Tailwind CSS, Zustand, `@xyflow/react` (React Flow), `@dnd-kit`, `@tanstack/react-query`.
- **Backend**: Python, FastAPI, SQLAlchemy, Pydantic, Pytest, PyInstaller.
- **Packaging**: Electron, Electron-Forge.

For live counts (blocks, routers, models, etc.), see `docs/REPO_FACTS.json` — regenerate with `python scripts/generate_repo_facts.py`.

## Core Concepts

### 1. Canvas & React Flow
The core of Blueprint is the visual pipeline builder (Canvas).
- Nodes on the frontend correspond to "Blocks" on the backend.
- Edges define the flow of execution and data.

### 2. Backend Blocks
Blocks are Python execution units located in `blocks/` at the repo root (referenced as `BUILTIN_BLOCKS_DIR` in `backend/config.py`). Each block is a directory containing `block.yaml` (metadata, ports, defaults) and `run.py` (execution logic).

To add a new Block:
1. Create a directory under the appropriate `blocks/<category>/` folder.
2. Add a `block.yaml` with metadata, input/output port definitions, and default config.
3. Add a `run.py` that uses `BlockContext` (from `backend/block_sdk/context.py`) with `load_input()`, `save_output()`, `log_metric()`, and `report_progress()`.
4. Run `python scripts/generate_block_registry.py` to update the frontend registry.

**Example Minimal Block Structure:**
```python
class MyCustomBlock(BaseBlock):
    type: str = "MyCustomBlock"
    parameters: dict = Field(default_factory=dict)

    def execute(self, inputs: dict) -> dict:
        # Do processing
        return {"output_key": "result"}
```

### 3. Frontend Nodes
Every backend Block requires a visual Node in `@xyflow/react` (React Flow).
Nodes are registered in the frontend nodeTypes. They use custom UI components with `Handle` components for incoming/outgoing edges.

**Example Minimal Node Component:**
```tsx
import { Handle, Position } from '@xyflow/react';

export function CustomNode({ data }) {
  return (
    <div className="bg-surface2 p-4 rounded border border-border">
      <Handle type="target" position={Position.Left} />
      <div>{data.label}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
```

### 4. Custom API Endpoints
If your block requires custom interactions (like uploading a file or triggering a specific long-running process out-of-band), add a new router to `backend/routers/` and `app.include_router` it in `backend/main.py`.

## Instructing your LLM
If you want your LLM to build a new feature, prompt it by copy-pasting this file along with the following instructions:
> *"I want to build a new module for the Blueprint app called [Module Name]. Based on the architecture outlined above, please generate the required Python FastAPI backend block code, the React Flow node component, and any necessary API routers."*
