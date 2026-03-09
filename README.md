# Blueprint — ML Experiment Workbench

**by Specific Labs**

A local-first ML experiment workbench for building, running, and analyzing machine learning pipelines. Blueprint gives you a visual canvas to wire together data loading, preprocessing, model training, evaluation, and more — all from your desktop.

<!-- ![Blueprint Screenshot](docs/screenshot.png) -->

---

## Features

- **Visual Pipeline Editor** — Drag-and-drop canvas powered by React Flow to design ML workflows
- **20+ Block Types** — Data loaders, transformers, model trainers, evaluators, exporters, and more
- **Real-Time Execution Monitoring** — Watch your pipeline run step by step with live status and logs
- **Model Hub** — Browse and pull models from Hugging Face, Ollama, and local sources
- **Results & Metrics Dashboard** — Interactive charts and tables for accuracy, loss, confusion matrices, and custom metrics
- **Paper Writing Tool** — Draft experiment write-ups alongside your results
- **Local-First** — Runs entirely on your machine with support for Ollama and MLX for local LLM inference

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10+ |
| Node.js | 18+ |
| Ollama *(optional)* | Latest — for local LLM inference |

---

## Quick Start

```bash
git clone https://github.com/specific-labs/blueprint.git
cd blueprint
./launch.sh
```

That's it. The launch script automatically:

- Creates a Python virtual environment (`.venv`)
- Installs backend and frontend dependencies
- Starts the FastAPI backend and Vite dev server
- Opens Blueprint in your default browser

Blueprint will be running at **http://localhost:4174** (or the next available port).

---

## Electron Desktop App (Optional)

For a standalone desktop experience:

```bash
cd frontend
npm run electron:dev
```

This launches Blueprint as a native Electron application with the backend bundled in.

---

## Production Build

### Backend (PyInstaller)

```bash
cd backend
pyinstaller blueprint_backend.spec
```

The standalone binary is written to `dist/`.

### Desktop App (Electron Forge)

```bash
cd frontend
npm run electron:make
```

Produces platform-specific installers in `frontend/out/make/`.

---

## Project Structure

```
blueprint/
├── launch.sh               # One-command launcher
├── backend/                # FastAPI backend
│   ├── main.py             # Application entry point
│   ├── models/             # SQLAlchemy models
│   ├── routers/            # API route handlers
│   ├── engine/             # Pipeline execution engine
│   ├── services/           # Business logic
│   ├── alembic/            # Database migrations
│   └── requirements.txt
├── frontend/               # React + Vite frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── stores/         # Zustand state stores
│   │   ├── pages/          # Top-level page views
│   │   └── lib/            # Block registry, utilities
│   ├── electron/           # Electron main process
│   └── package.json
├── blocks/                 # ML block implementations
│   ├── training/           # LoRA, QLoRA, DPO, full fine-tuning
│   ├── merge/              # SLERP, TIES, DARE, mergekit
│   ├── evaluation/         # lm-eval harness, MMLU
│   ├── data/               # Loaders, tokenizers, splitters
│   └── ...                 # 20+ block categories
└── README.md
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18, TypeScript, Vite |
| State Management | Zustand |
| Pipeline Canvas | React Flow |
| Charts | Recharts |
| Code Editor | Monaco Editor |
| Animations | Framer Motion |
| Backend | FastAPI, SQLAlchemy, SQLite |
| Desktop | Electron 34 |

---

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
