import { T, F, FS } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import { Hammer, Code, FlaskConical, Upload } from 'lucide-react'
import { helpCard as card, helpBody as body, helpTip as tip, helpStepList as stepList, helpCode as code, helpCodeBlock as codeBlock } from './styles'

export const BLOCK_WORKSHOP_TEXT = `Block Workshop. The Block Workshop lets you create, edit, test, and deploy custom blocks without leaving Blueprint. Custom blocks extend the built-in block library with your own logic. Creating a Block: Open the Workshop from the sidebar. Click "+ NEW" to start a fresh block. Fill in the block metadata: Name (display name), Description, Category (external, data, model, inference, training, metrics, embedding, utilities, agents, interventions, endpoints), and Icon (any Lucide icon name). Define input and output ports — each has an ID, label, and data type (dataset, text, model, config, metrics, embedding, artifact, agent, llm, any). Add config fields with a name, label, and type (string, integer, float, boolean, select, text_area, file_path). Writing Block Code: The code editor provides a Python template with a run() function. Two signatures are supported: run(ctx) — modern style receiving a BlockContext with .config, .inputs, .set_output(), .log(), .progress(). run(inputs, config) — legacy style receiving dicts directly. The code runs in a subprocess at execution time, isolated from the main process. Testing & Validation: Click "TEST BLOCK" to validate your code without executing it. Validation checks: Python syntax correctness, presence of a run() function with the right signature, detection of risky imports (subprocess, ctypes, pty, atexit), and warnings about top-level statements that run on import rather than execution. Saving & Deployment: When you save a block, it is stored both locally (localStorage for the frontend block registry) and on the backend filesystem (~/.specific-labs/custom_blocks/{type_id}/block.yaml + run.py). This dual sync ensures the block appears in the Block Library and is executable by the pipeline engine. Live Preview: The workshop shows a real-time visual preview of your block as it will appear on the canvas, plus a YAML preview of the block definition structure. Block SDK: Custom blocks have access to the full Block SDK — BlockContext provides load_input(), save_output(), log_message(), log_metric(), report_progress(), and resolve_* helper methods for flexible input handling.`

export default function BlockWorkshop() {
  return (
    <div>
      <SectionAnchor id="block-workshop" title="Block Workshop" level={1}>
        <Hammer size={22} color={T.cyan} />
      </SectionAnchor>

      {/* Creating a Block */}
      <SectionAnchor id="block-workshop/creating" title="Creating a Block" level={2} />
      <div style={card}>
        <p style={body}>
          The Block Workshop lets you create custom blocks that extend Blueprint&apos;s built-in
          library with your own logic. Open it from the sidebar navigation.
        </p>
        <ol style={stepList}>
          <li>Click <strong>+ NEW</strong> to start a fresh block</li>
          <li>Set a <strong>Name</strong>, <strong>Description</strong>, and <strong>Category</strong></li>
          <li>Choose an <strong>Icon</strong> (any Lucide icon name, e.g. <span style={code}>Brain</span>, <span style={code}>Zap</span>)</li>
          <li>Define <strong>Input Ports</strong> — each with an ID, label, and data type</li>
          <li>Define <strong>Output Ports</strong> — same structure as inputs</li>
          <li>Optionally add <strong>Config Fields</strong> for user-configurable parameters</li>
        </ol>
        <div style={tip}>
          Port data types determine which blocks can connect to each other. Use <span style={code}>any</span> for
          maximum flexibility, or specific types like <span style={code}>dataset</span>, <span style={code}>text</span>, <span style={code}>model</span> for type safety.
        </div>
      </div>

      {/* Writing Code */}
      <SectionAnchor id="block-workshop/code" title="Writing Block Code" level={2} />
      <div style={card}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <Code size={14} color={T.cyan} />
          <span style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text }}>
            run.py
          </span>
        </div>
        <p style={body}>
          Your block code must define a <span style={code}>run()</span> function. Two signatures
          are supported:
        </p>
        <div style={codeBlock}>
{`# Modern style — BlockContext
def run(ctx):
    data = ctx.inputs.get("input")
    ctx.log("Processing...")
    ctx.progress(0.5)
    ctx.set_output("output", result)

# Legacy style — plain dicts
def run(inputs, config):
    data = inputs.get("input")
    return {"output": result}`}
        </div>
        <p style={{ ...body, marginTop: 10 }}>
          The <span style={code}>BlockContext</span> object provides:
        </p>
        <ul style={stepList}>
          <li><span style={code}>ctx.config</span> — dict of configuration values</li>
          <li><span style={code}>ctx.inputs</span> — dict of input port data</li>
          <li><span style={code}>ctx.set_output(port_id, data)</span> — set output port value</li>
          <li><span style={code}>ctx.log(message)</span> — emit a log message (visible in Monitor)</li>
          <li><span style={code}>ctx.progress(fraction)</span> — report progress (0.0 – 1.0)</li>
          <li><span style={code}>ctx.log_metric(name, value)</span> — log a numeric metric</li>
        </ul>
      </div>

      {/* Testing */}
      <SectionAnchor id="block-workshop/testing" title="Testing & Validation" level={2} />
      <div style={card}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <FlaskConical size={14} color={T.purple} />
          <span style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text }}>
            Code Validation
          </span>
        </div>
        <p style={body}>
          Click <strong>TEST BLOCK</strong> to validate your code without executing it.
          The validator checks:
        </p>
        <ul style={stepList}>
          <li><strong>Syntax</strong> — Python AST parsing catches syntax errors with line numbers</li>
          <li><strong>run() function</strong> — must exist with 1-2 positional arguments</li>
          <li><strong>Risky imports</strong> — warns about subprocess, ctypes, pty, atexit</li>
          <li><strong>Top-level code</strong> — warns about statements outside functions that run on import</li>
        </ul>
        <div style={tip}>
          For full execution testing, save the block first. The backend can then run it in an
          isolated subprocess with a 30-second timeout via the test endpoint.
        </div>
      </div>

      {/* Saving & Deployment */}
      <SectionAnchor id="block-workshop/deployment" title="Saving & Deployment" level={2} />
      <div style={card}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <Upload size={14} color={T.green} />
          <span style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text }}>
            Dual Sync
          </span>
        </div>
        <p style={body}>
          When you click <strong>SAVE</strong>, the block is stored in two places:
        </p>
        <ul style={stepList}>
          <li><strong>Frontend</strong> — localStorage registry so the block appears in the Block Library immediately</li>
          <li><strong>Backend</strong> — filesystem at <span style={code}>~/.specific-labs/custom_blocks/&#123;type_id&#125;/</span> with
            {' '}<span style={code}>block.yaml</span> (metadata) and <span style={code}>run.py</span> (code)</li>
        </ul>
        <p style={body}>
          This dual sync ensures custom blocks are both visible in the UI and executable by the
          pipeline engine. The block type ID is auto-generated from the name and must match the
          pattern <span style={code}>[a-z][a-z0-9_]&#123;0,63&#125;</span>.
        </p>
        <div style={tip}>
          To delete a block, select it in the left sidebar and click the trash icon. This removes
          it from both localStorage and the backend filesystem.
        </div>
      </div>
    </div>
  )
}
