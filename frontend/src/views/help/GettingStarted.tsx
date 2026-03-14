import { T, F, FS } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import { Rocket, Monitor, Download, ToggleLeft, Play } from 'lucide-react'
import { helpCard as card, helpBody as body, helpTip as tip, helpStepList as stepList, helpCode as code } from './styles'

export const GETTING_STARTED_TEXT = `What is Blueprint? Blueprint is a local-first ML experiment workbench that lets you visually build, run, and analyze machine learning pipelines using a drag-and-drop canvas with 135+ block types. It runs entirely on your machine — no cloud, no accounts, no data leaves your computer. System Requirements: Python 3.10+, Node.js 18+, macOS (Apple Silicon recommended), Linux, or Windows. Optional: Ollama for local LLM inference, MLX for Apple Silicon training. 16GB+ RAM recommended (8GB minimum for inference-only). Installation: git clone, then run ./launch.sh which auto-creates venv, installs deps, and starts both servers. Electron desktop app: cd frontend && npm run electron:dev. Data location: ~/.specific-labs/ (database, models, artifacts, plugins, logs). Simple vs Professional Mode: Settings → UI Mode toggle. Simple Mode shows core workflow only — data, training, inference, evaluation, output categories. Hides plugins, export connectors, config inheritance badges, Paper tool, Control Tower. Professional Mode shows all block categories, plugin panels, export connectors, config inheritance visualization, advanced monitoring. First Pipeline Walkthrough: Create project → open pipeline editor → drag Text Input block → drag LLM Inference block → connect them → configure model name → click Run → view results.`

export default function GettingStarted() {
  return (
    <div>
      <SectionAnchor id="getting-started" title="Getting Started" level={1}>
        <Rocket size={22} color={T.accent} />
      </SectionAnchor>

      {/* 1.1 What is Blueprint */}
      <SectionAnchor id="getting-started/what-is-blueprint" title="What is Blueprint?" level={2} />
      <div style={card}>
        <p style={body}>
          Blueprint is a local-first ML experiment workbench by Specific Labs that lets you visually
          build, run, and analyze machine learning pipelines using a drag-and-drop canvas with 135+
          block types across 9 categories. It runs entirely on your machine — no cloud accounts, no
          data leaves your computer.
        </p>
        <div style={tip}>
          <strong>Why local-first?</strong> Full privacy, no API costs for local models, works
          offline, and you own all your data and artifacts.
        </div>
      </div>

      {/* 1.2 System Requirements */}
      <SectionAnchor id="getting-started/system-requirements" title="System Requirements" level={2}>
        <Monitor size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <ul style={stepList}>
          <li>
            <strong>Python 3.10+</strong> and <strong>Node.js 18+</strong>
          </li>
          <li>macOS (Apple Silicon recommended), Linux, or Windows</li>
          <li>
            <strong>Optional:</strong> Ollama for local LLM inference, MLX for Apple Silicon
            training
          </li>
          <li>16GB+ RAM recommended (8GB minimum for inference-only workflows)</li>
        </ul>
        <div style={tip}>
          Apple Silicon Macs get the best experience: Metal GPU acceleration for PyTorch, native MLX
          support, and optimized Ollama performance.
        </div>
      </div>

      {/* 1.3 Installation */}
      <SectionAnchor id="getting-started/installation" title="Installation" level={2}>
        <Download size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <ol style={stepList}>
          <li>
            Clone the repo: <span style={code}>git clone https://github.com/santiagoaraoz2001-sketch/blueprint.git</span>
          </li>
          <li>
            Run <span style={code}>./launch.sh</span> — this auto-creates a Python venv, installs
            all dependencies, and starts both the backend and frontend servers.
          </li>
          <li>
            For the Electron desktop app: <span style={code}>cd frontend && npm run electron:dev</span>
          </li>
        </ol>
        <p style={{ ...body, marginTop: 12 }}>
          <strong>Data location:</strong> All data is stored in{' '}
          <span style={code}>~/.specific-labs/</span> including the SQLite database, model
          artifacts, plugins, custom blocks, and logs.
        </p>
        <div style={tip}>
          The launch script is idempotent — running it again won&apos;t reinstall deps if they&apos;re
          already present.
        </div>
      </div>

      {/* 1.4 Simple vs Professional Mode */}
      <SectionAnchor
        id="getting-started/mode-toggle"
        title="Simple vs Professional Mode"
        level={2}
      >
        <ToggleLeft size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>Where:</strong> Settings → UI Mode toggle
        </p>
        <div style={{ display: 'flex', gap: 16, marginTop: 14 }}>
          <div style={{ flex: 1, padding: 14, background: T.surface1, border: `1px solid ${T.border}` }}>
            <div
              style={{
                fontFamily: F,
                fontSize: FS.sm,
                fontWeight: 700,
                color: T.fg,
                marginBottom: 8,
              }}
            >
              Simple Mode
            </div>
            <ul style={{ ...stepList, fontSize: FS.xs, color: T.dim }}>
              <li>Core workflow: data, training, inference, evaluation, output</li>
              <li>Clean, focused interface</li>
              <li>Hides: plugins, export connectors, config inheritance badges, Paper, Control Tower</li>
            </ul>
          </div>
          <div style={{ flex: 1, padding: 14, background: T.surface1, border: `1px solid ${T.border}` }}>
            <div
              style={{
                fontFamily: F,
                fontSize: FS.sm,
                fontWeight: 700,
                color: T.fg,
                marginBottom: 8,
              }}
            >
              Professional Mode
            </div>
            <ul style={{ ...stepList, fontSize: FS.xs, color: T.dim }}>
              <li>All 135+ blocks across all categories</li>
              <li>Plugin panels, export connectors</li>
              <li>Config inheritance visualization, advanced monitoring</li>
            </ul>
          </div>
        </div>
        <div style={tip}>
          First launch shows a welcome modal to choose your mode. You can switch anytime in Settings.
        </div>
      </div>

      {/* 1.5 First Pipeline Walkthrough */}
      <SectionAnchor
        id="getting-started/first-pipeline"
        title="First Pipeline Walkthrough"
        level={2}
      >
        <Play size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <ol style={stepList}>
          <li>
            <strong>Create a project</strong> — Click &ldquo;NEW PROJECT&rdquo; on the Dashboard. Give it a
            name and description.
          </li>
          <li>
            <strong>Open the Pipeline Editor</strong> — Navigate to the Pipeline Editor view.
          </li>
          <li>
            <strong>Add a Text Input block</strong> — Open the block library (left panel), find
            &ldquo;Text Input&rdquo; under Data, and drag it onto the canvas.
          </li>
          <li>
            <strong>Add an LLM Inference block</strong> — Drag &ldquo;LLM Inference&rdquo; from the Inference
            category onto the canvas.
          </li>
          <li>
            <strong>Connect them</strong> — Drag from the Text Input&apos;s output port (right side) to
            the LLM Inference&apos;s input port (left side).
          </li>
          <li>
            <strong>Configure</strong> — Click the LLM Inference block and set the model name in the
            config panel (e.g., &ldquo;llama3.2&rdquo; for Ollama).
          </li>
          <li>
            <strong>Run</strong> — Click the green &ldquo;Run&rdquo; button in the toolbar.
          </li>
          <li>
            <strong>View results</strong> — Switch to the Results view to see the output, timing, and
            logs.
          </li>
        </ol>
        <div style={tip}>
          Hover over any port to see its data type. Port colors match: green=dataset, pink=text,
          violet=model, cyan=config, amber=metrics.
        </div>
      </div>
    </div>
  )
}
