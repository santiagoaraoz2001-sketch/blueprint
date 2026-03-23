# Blueprint Developer Architecture & Syntax

This document is designed to be fed directly into an LLM (like Claude or GPT-4) when you want to write custom Modules, Blocks, or Workflows for the Blueprint app.

## Project Structure
- **Frontend**: React, TypeScript, Vite, Tailwind CSS, Zustand, `@xyflow/react` (React Flow), `@dnd-kit`, `@tanstack/react-query`.
- **Backend**: Python, FastAPI, SQLAlchemy, Pydantic, Pytest, PyInstaller.
- **Packaging**: Electron, Electron-Forge.

## Core Concepts

### 1. Canvas & React Flow
The core of Blueprint is the visual pipeline builder (Canvas).
- Nodes on the frontend correspond to "Blocks" on the backend.
- Edges define the flow of execution and data.

### 2. Backend Blocks
Blocks are python execution units located in `backend/blocks/`. 
To add a new Block:
1. Inherit from a base Block schema (e.g., `BaseBlock`).
2. Implement an `execute()` method that takes inputs from incoming edges and returns an output payload.
3. Register the block in the execution DAG router.

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
