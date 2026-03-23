import { T } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import {
  GitBranch,
  Move,
  Library,
  Sliders,
  LayoutTemplate,
  ShieldCheck,
  Play,
  RotateCcw,
  Grid3x3,
  StickyNote,
  Command,
} from 'lucide-react'
import { helpCard as card, helpBody as body, helpTip as tip, helpStepList as stepList, helpCode as code } from './styles'

export const PIPELINE_EDITOR_TEXT = `Canvas Basics. Drag blocks from the block library onto the canvas. Connect blocks by dragging from output port to input port. Ports are color-coded by data type: green=dataset, pink=text, violet=model, cyan=config, amber=metrics, teal=embedding, red=artifact, sky=agent, gold=llm. Zoom: Cmd+/Cmd- or scroll wheel. Pan: hold Space + drag. Fit: Cmd+0. Minimap in bottom-right corner. Block Library. 118 blocks across 9 categories. Categories: data, training, inference, evaluation, merge, flow, agents, endpoints, output. Search blocks by name, description, or tags. Each block has a maturity badge: stable, beta, experimental. Block Configuration. Click any block to open its config panel. Config fields are typed: string, integer, float, boolean, select, multiselect, file_path, text_area. Config Inheritance: Some fields (seed, text_column, trust_remote_code) auto-propagate from upstream blocks. Inherited fields show a blue left border and Inherited from badge. Click unlink icon to override. Inheritance Overlay shows which downstream blocks inherit a value. Pipeline Templates. Click Templates button in the toolbar. Template gallery shows pre-wired pipelines. Each template has variables you fill in. Templates auto-layout using dagre. Pipeline Validation. Click the shield icon (Cmd+Shift+V). Checks: empty pipeline, duplicate IDs, cycles, disconnected blocks, missing required inputs, type mismatches. Running Pipelines. Click the green Run button. Blocks execute in topological order. Real-time progress with ETA countdown. SSE connection status badge. Cancel anytime. Re-Run from Node (Partial Re-Execution). Right-click any node then Re-run from here. Upstream nodes use cached outputs. Target node and downstream re-execute. Config diff preview shows what changed. Shift+R keyboard shortcut. Parameter Sweeps. Right-click a node then Parameter Sweep. Define parameter ranges. Grid search or Random search. Sweep Heatmap in Results. Best Config badge. Sweeps run up to 4 parallel. Sticky Notes and Groups. Annotate canvas with sticky notes. Group related blocks. Command Palette. Cmd+K opens command palette. Quick-search for blocks, pipelines, actions.`

export default function PipelineEditor() {
  return (
    <div>
      <SectionAnchor id="pipeline-editor" title="Pipeline Editor" level={1}>
        <GitBranch size={22} color={T.cyan} />
      </SectionAnchor>

      {/* 3.1 Canvas Basics */}
      <SectionAnchor id="pipeline-editor/canvas" title="Canvas Basics" level={2}>
        <Move size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> The canvas is your visual workspace for building ML pipelines by
          connecting blocks.
        </p>
        <ul style={stepList}>
          <li>Drag blocks from the block library (left panel) onto the canvas</li>
          <li>Connect blocks by dragging from an output port (right side) to an input port (left side)</li>
          <li>
            Ports are color-coded by data type: <span style={{ color: '#22c55e' }}>green</span>=dataset,{' '}
            <span style={{ color: '#ec4899' }}>pink</span>=text,{' '}
            <span style={{ color: '#8b5cf6' }}>violet</span>=model,{' '}
            <span style={{ color: '#06b6d4' }}>cyan</span>=config,{' '}
            <span style={{ color: '#f59e0b' }}>amber</span>=metrics,{' '}
            <span style={{ color: '#14b8a6' }}>teal</span>=embedding,{' '}
            <span style={{ color: '#ef4444' }}>red</span>=artifact,{' '}
            <span style={{ color: '#0ea5e9' }}>sky</span>=agent,{' '}
            <span style={{ color: '#E8A030' }}>gold</span>=llm
          </li>
          <li>
            <strong>Zoom:</strong> <span style={code}>Cmd+</span>/<span style={code}>Cmd-</span> or scroll wheel.{' '}
            <strong>Pan:</strong> hold <span style={code}>Space</span> + drag.{' '}
            <strong>Fit:</strong> <span style={code}>Cmd+0</span>
          </li>
          <li>Minimap in the bottom-right corner helps navigate large pipelines</li>
        </ul>
      </div>

      {/* 3.2 Block Library */}
      <SectionAnchor id="pipeline-editor/block-library" title="Block Library" level={2}>
        <Library size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> 118 blocks across 9 categories (12 including composite/plugin
          blocks), searchable by name, description, or tags.
        </p>
        <ul style={stepList}>
          <li>
            Categories: data, training, inference, evaluation, merge, flow, agents, endpoints,
            output
          </li>
          <li>
            Each block has a maturity badge: <span style={{ color: '#22c55e' }}>stable</span>,{' '}
            <span style={{ color: '#f59e0b' }}>beta</span>,{' '}
            <span style={{ color: '#ef4444' }}>experimental</span>
          </li>
          <li>Search by typing in the block library search bar</li>
          <li>Drag directly from the library to the canvas to add a block</li>
        </ul>
        <div style={tip}>
          Use the search bar in the block library to quickly find blocks. Searching &ldquo;merge&rdquo; shows all
          merge strategies (SLERP, TIES, DARE, etc.).
        </div>
      </div>

      {/* 3.3 Block Configuration */}
      <SectionAnchor id="pipeline-editor/config" title="Block Configuration" level={2}>
        <Sliders size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Each block has typed configuration fields that control its behavior.
        </p>
        <ul style={stepList}>
          <li>Click any block to open its config panel on the right</li>
          <li>
            Fields are typed: string, integer, float, boolean, select, multiselect, file_path,
            text_area. The <span style={code}>file_path</span> type opens a native file/directory
            picker dialog.
          </li>
          <li>Fields show descriptions, defaults, and min/max bounds</li>
        </ul>
        <p style={{ ...body, marginTop: 12 }}>
          <strong>Config Inheritance:</strong> Certain keys (<span style={code}>seed</span>,{' '}
          <span style={code}>text_column</span>, <span style={code}>trust_remote_code</span>)
          auto-propagate from upstream blocks through the DAG.
        </p>
        <ul style={stepList}>
          <li>Inherited fields show a blue left border and &ldquo;Inherited from [Node Name]&rdquo; badge</li>
          <li>Click the unlink icon to override an inherited value</li>
          <li>Click the link icon to restore inheritance from upstream</li>
          <li>
            <strong>Inheritance Overlay:</strong> Click any propagatable field → canvas enters
            overlay mode showing which downstream blocks inherit that value. Blue dots = inheriting,
            orange dots = overridden, green dot = origin. Press{' '}
            <span style={code}>Escape</span> to exit.
          </li>
        </ul>
        <div style={tip}>
          Config inheritance eliminates repetition. Set <span style={code}>seed: 42</span> once on
          your data loader, and every downstream block inherits it automatically.
        </div>
      </div>

      {/* 3.4 Pipeline Templates */}
      <SectionAnchor id="pipeline-editor/templates" title="Pipeline Templates" level={2}>
        <LayoutTemplate size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Pre-wired pipeline blueprints you can customize with your own
          models and data.
        </p>
        <ul style={stepList}>
          <li>Click &ldquo;Templates&rdquo; button in the toolbar</li>
          <li>
            Available templates: &ldquo;Fine-Tune a LoRA&rdquo;, &ldquo;Evaluate a Model&rdquo;,
            &ldquo;Build a RAG Pipeline&rdquo;, &ldquo;Merge Two Models&rdquo;, &ldquo;Train, Evaluate, and
            Publish&rdquo;
          </li>
          <li>Each template has variable slots you fill in (base model, dataset, learning rate, etc.)</li>
          <li>Select template → fill variables → pipeline appears fully wired on the canvas</li>
          <li>Templates auto-layout nodes left-to-right using dagre</li>
          <li>Difficulty badges: beginner, intermediate, advanced. Estimated time shown.</li>
        </ul>
        <div style={tip}>
          Templates are the fastest way to start. Pick a template, fill in your model name and
          dataset, and you have a working pipeline in seconds.
        </div>
      </div>

      {/* 3.5 Pipeline Validation */}
      <SectionAnchor id="pipeline-editor/validation" title="Pipeline Validation" level={2}>
        <ShieldCheck size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Pre-run checks that catch configuration errors before execution.
        </p>
        <p style={{ ...body, marginTop: 8 }}>
          <strong>How:</strong> Click the shield icon in the toolbar (or{' '}
          <span style={code}>Cmd+Shift+V</span>).
        </p>
        <ul style={stepList}>
          <li>Checks: empty pipeline, duplicate IDs, cycles, disconnected blocks</li>
          <li>Validates: required inputs connected, type mismatches, missing critical config</li>
          <li>Estimates runtime per block category</li>
          <li>Click any issue to focus the affected block on the canvas</li>
          <li>Validation also runs automatically before each pipeline run</li>
        </ul>
      </div>

      {/* 3.6 Running Pipelines */}
      <SectionAnchor id="pipeline-editor/running" title="Running Pipelines" level={2}>
        <Play size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>How:</strong> Click the green &ldquo;Run&rdquo; button in the toolbar.
        </p>
        <ul style={stepList}>
          <li>Blocks execute in topological order (upstream first)</li>
          <li>Real-time progress: each block shows a progress bar, overall progress at top, ETA countdown</li>
          <li>
            SSE connection status badge: <span style={{ color: '#22c55e' }}>Live</span> (green),{' '}
            <span style={{ color: '#eab308' }}>Reconnecting</span> (yellow),{' '}
            <span style={{ color: '#ef4444' }}>Connection lost</span> (red)
          </li>
          <li>Cancel anytime with the Stop button. Cancelled runs save partial outputs.</li>
        </ul>
      </div>

      {/* 3.7 Re-Run from Node */}
      <SectionAnchor
        id="pipeline-editor/rerun-from-node"
        title="Re-Run from Node (Partial Re-Execution)"
        level={2}
      >
        <RotateCcw size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Re-execute part of a completed pipeline without re-running upstream
          blocks.
        </p>
        <ul style={stepList}>
          <li>After a run completes, right-click any node → &ldquo;Re-run from here&rdquo;</li>
          <li>Upstream nodes use cached outputs from the previous run (grayed out with lock icon)</li>
          <li>Target node and all downstream nodes re-execute with fresh computation</li>
          <li>Edit config on the target node before re-running — a diff preview shows what changed</li>
          <li>Floating action bar: [Cancel] [Re-run from Node →]</li>
          <li>New run metadata links to the source run</li>
          <li>
            Keyboard shortcut: <span style={code}>Shift+R</span> while a node is selected
          </li>
        </ul>
        <p style={{ ...body, marginTop: 8 }}>
          <strong>Why:</strong> Change an inference prompt and re-run in 5 seconds instead of
          re-loading data for 5 minutes. Only the work that needs to happen actually runs.
        </p>
        <div style={tip}>
          Results view shows &ldquo;Reused outputs from Run #xyz for nodes A, B&rdquo; so you always know
          what was cached vs. freshly computed.
        </div>
      </div>

      {/* 3.8 Parameter Sweeps */}
      <SectionAnchor id="pipeline-editor/sweeps" title="Parameter Sweeps" level={2}>
        <Grid3x3 size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Automatically run a pipeline with many different parameter
          combinations to find the optimal config.
        </p>
        <ul style={stepList}>
          <li>Right-click a node → &ldquo;Parameter Sweep&rdquo; (or from the toolbar)</li>
          <li>Define parameter ranges: numbers get min/max/step, selects get multi-choice</li>
          <li>Choose search type: Grid (all combinations) or Random (N samples from distributions)</li>
          <li>Select which metric to optimize (e.g., eval_accuracy, loss)</li>
          <li>Click &ldquo;Start Sweep&rdquo; → Blueprint creates one run per config combination</li>
          <li>Sweep Heatmap appears in Results — a colored grid showing metric values</li>
          <li>&ldquo;Best Config&rdquo; badge highlights the winning combination</li>
          <li>Sweeps can run up to 4 configs in parallel</li>
        </ul>
        <div style={tip}>
          Start with a coarse grid sweep (few values per parameter) to find the interesting region,
          then run a finer sweep around the best area.
        </div>
      </div>

      {/* 3.9 Sticky Notes & Groups */}
      <SectionAnchor id="pipeline-editor/annotations" title="Sticky Notes & Groups" level={2}>
        <StickyNote size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          Annotate your canvas with sticky notes for documentation. Group related blocks together for
          visual organization. Both are purely visual and don&apos;t affect execution.
        </p>
      </div>

      {/* 3.10 Command Palette */}
      <SectionAnchor id="pipeline-editor/command-palette" title="Command Palette" level={2}>
        <Command size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          Press <span style={code}>Cmd+K</span> to open the command palette. Quick-search for
          blocks, pipelines, and actions. Start typing to filter, then press Enter to select.
        </p>
      </div>
    </div>
  )
}
