import { T } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import { Upload, BarChart3, Globe, FileText, Plug } from 'lucide-react'
import { helpCard as card, helpBody as body, helpTip as tip, helpStepList as stepList, helpCode as code } from './styles'

export const EXPORT_CONNECTORS_TEXT = `Export Connectors. Push run data to external services with one click. Access via Results view Export dropdown on any completed run. Weights & Biases: API key, project name, entity. Exports all metrics (timeseries), run config, artifacts. Returns W&B run URL. Requires pip install wandb. HuggingFace Hub: HF token, repo ID, private boolean, commit message. Exports model artifacts + auto-generated model card. Model card includes training config, benchmark results, provenance, license. Requires pip install huggingface_hub. Jupyter Notebook: output directory, include visualizations, include raw data. Generates .ipynb with cells: header, config, data loading, metrics table, visualization, reproduction code. No external service needed. Requires pip install nbformat. Connectors API: GET /api/connectors/ lists all registered connectors. POST /api/connectors/{name}/validate validates config. POST /api/connectors/runs/{run_id}/export/{name} triggers export.`

export default function ExportConnectors() {
  return (
    <div>
      <SectionAnchor id="export-connectors" title="Export Connectors" level={1}>
        <Upload size={22} color={T.cyan} />
      </SectionAnchor>

      {/* 7.1 Overview */}
      <SectionAnchor id="export-connectors/overview" title="Overview" level={2}>
        <Plug size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          Export connectors push run data to external services with one click. Access via the Results
          view → &ldquo;Export&rdquo; dropdown on any completed run.
        </p>
        <div style={tip}>
          All connectors consume the standardized{' '}
          <span style={code}>run-export.json</span> format, ensuring consistent data regardless of
          the destination.
        </div>
      </div>

      {/* 7.2 Weights & Biases */}
      <SectionAnchor id="export-connectors/wandb" title="Weights & Biases" level={2}>
        <BarChart3 size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>Config:</strong> API key, project name, entity (optional), run name (optional).
        </p>
        <ul style={stepList}>
          <li>Exports: all metrics (timeseries), run config, artifacts</li>
          <li>Returns: W&B run URL (clickable link to your W&B dashboard)</li>
          <li>
            Requires: <span style={code}>pip install wandb</span>
          </li>
        </ul>
        <div style={tip}>
          Set your W&B API key once in Settings → Export Connectors. It persists across sessions.
        </div>
      </div>

      {/* 7.3 HuggingFace Hub */}
      <SectionAnchor id="export-connectors/huggingface" title="HuggingFace Hub" level={2}>
        <Globe size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>Config:</strong> HF token, repo ID (e.g., &ldquo;SpecificAI/my-model&rdquo;),
          private (boolean), commit message.
        </p>
        <ul style={stepList}>
          <li>Exports: model artifacts + auto-generated model card</li>
          <li>
            Model card includes: training config, benchmark results, provenance (Blueprint run ID),
            license
          </li>
          <li>
            Requires: <span style={code}>pip install huggingface_hub</span>
          </li>
        </ul>
        <div style={tip}>
          The auto-generated model card is publication-ready and includes all metadata from your
          Blueprint run.
        </div>
      </div>

      {/* 7.4 Jupyter Notebook */}
      <SectionAnchor id="export-connectors/jupyter" title="Jupyter Notebook" level={2}>
        <FileText size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>Config:</strong> output directory, include visualizations (boolean), include raw
          data (boolean).
        </p>
        <ul style={stepList}>
          <li>
            Generates a <span style={code}>.ipynb</span> file with cells: header, config, data
            loading, metrics table, visualization (matplotlib), reproduction code
          </li>
          <li>No external service needed — writes to local filesystem</li>
          <li>
            Requires: <span style={code}>pip install nbformat</span>
          </li>
        </ul>
        <div style={tip}>
          Great for sharing reproducible results with colleagues who prefer notebooks over the
          Blueprint UI.
        </div>
      </div>

      {/* 7.5 API */}
      <SectionAnchor id="export-connectors/api" title="Connectors API" level={2}>
        <Plug size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <ul style={stepList}>
          <li>
            <span style={code}>GET /api/connectors/</span> — Lists all registered connectors with
            their config fields
          </li>
          <li>
            <span style={code}>POST /api/connectors/&#123;name&#125;/validate</span> — Validates
            config before export
          </li>
          <li>
            <span style={code}>POST /api/connectors/runs/&#123;run_id&#125;/export/&#123;name&#125;</span>{' '}
            — Triggers the export
          </li>
        </ul>
      </div>
    </div>
  )
}
