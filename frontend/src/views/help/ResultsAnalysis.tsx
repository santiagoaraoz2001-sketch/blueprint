import { T, F, FS } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import {
  BarChart3,
  Clock,
  Grid3x3,
  GitCompare,
  TestTube,
  History,
  FileJson,
} from 'lucide-react'
import { helpCard as card, helpBody as body, helpTip as tip, helpStepList as stepList, helpCode as code } from './styles'

export const RESULTS_ANALYSIS_TEXT = `Results View. Every pipeline run creates a results entry with timing, status, per-block outputs, logs, metrics. Charts auto-generate for numeric metrics. Compare metrics across runs. Checkpoint Timeline. Training runs with checkpoint_interval > 0 save checkpoints. Results shows a loss curve with clickable checkpoint markers. Click a checkpoint to see epoch, loss, accuracy, then Load as Model button. Sweep Heatmap. After parameter sweep, heatmap shows results as colored grid. Axes: two swept parameters. Cell color: metric value. Click any cell for run details. Best Config badge on optimal cell. Model Diff Visualization. After model_diff block, Results shows token-by-token comparison table, distribution bar chart, summary stats (KL divergence, top-1 agreement, cosine similarity). Significance Report. After ab_significance block, shows two-column layout with branch stats, p-value with color coding, Cohen's d with effect size label, 95% CI as error bar, verdict text. Run Comparison & Data Provenance. Compare any two runs: config diff shows changed parameters. Data provenance records SHA256 hashes of all input datasets. GET /runs/{id}/data-provenance and POST /runs/compare-data endpoints. Structured Export (run-export.json). Every completed run auto-generates run-export.json with run metadata, pipeline config, metrics, artifacts list, data provenance, environment info. Download via GET /runs/{id}/export/download.`

export default function ResultsAnalysis() {
  return (
    <div>
      <SectionAnchor id="results-analysis" title="Results & Analysis" level={1}>
        <BarChart3 size={22} color={T.accent} />
      </SectionAnchor>

      {/* 6.1 Results View */}
      <SectionAnchor id="results-analysis/results-view" title="Results View" level={2}>
        <BarChart3 size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Every pipeline run creates a results entry with timing, status,
          per-block outputs, logs, and metrics.
        </p>
        <ul style={stepList}>
          <li>Click a run to expand its details</li>
          <li>Compare metrics across runs with the comparison view</li>
          <li>Charts auto-generate for numeric metrics — hover for exact values</li>
          <li>Send any table or chart to the Paper tool with &ldquo;Add to Paper&rdquo;</li>
        </ul>
      </div>

      {/* 6.2 Checkpoint Timeline */}
      <SectionAnchor id="results-analysis/checkpoints" title="Checkpoint Timeline" level={2}>
        <Clock size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Training runs with{' '}
          <span style={code}>checkpoint_interval &gt; 0</span> save model checkpoints at regular
          intervals, visualized on a timeline.
        </p>
        <ul style={stepList}>
          <li>Results view shows a loss curve with clickable checkpoint markers</li>
          <li>Click a checkpoint → see epoch, loss, accuracy → &ldquo;Load as Model&rdquo; button</li>
          <li>
            &ldquo;Load as Model&rdquo; creates a model_selector node pre-configured with the
            checkpoint path
          </li>
        </ul>
        <p style={{ ...body, marginTop: 8 }}>
          <strong>Why:</strong> Train for 50 epochs, realize epoch 45 was the sweet spot, load that
          exact checkpoint without retraining.
        </p>
        <div style={tip}>
          Set <span style={code}>checkpoint_interval</span> in your training block config. Default
          is 0 (final model only). Set to 5 to save every 5 epochs.
        </div>
      </div>

      {/* 6.3 Sweep Heatmap */}
      <SectionAnchor id="results-analysis/sweep-heatmap" title="Sweep Heatmap" level={2}>
        <Grid3x3 size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> After a parameter sweep completes, the heatmap visualizes all
          results as a colored grid.
        </p>
        <ul style={stepList}>
          <li>Axes: any two swept parameters</li>
          <li>
            Cell color: metric value (
            <span style={{ color: '#22c55e' }}>green</span> = good,{' '}
            <span style={{ color: '#ef4444' }}>red</span> = bad)
          </li>
          <li>Click any cell to open that run&apos;s full details</li>
          <li>&ldquo;Best Config&rdquo; badge on the optimal cell</li>
        </ul>
        <div style={tip}>
          Heatmaps are great for visualizing hyperparameter interactions — e.g., &ldquo;high learning rate
          + small batch size produces the best accuracy.&rdquo;
        </div>
      </div>

      {/* 6.4 Model Diff Visualization */}
      <SectionAnchor id="results-analysis/model-diff" title="Model Diff Visualization" level={2}>
        <GitCompare size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> After running a <span style={code}>model_diff</span> block, Results
          shows a detailed comparison between two models.
        </p>
        <ul style={stepList}>
          <li>Token-by-token comparison table: position, Model A prediction, Model B prediction, probability diff, KL divergence</li>
          <li>Distribution bar chart for selected token positions</li>
          <li>Summary stats: overall KL divergence, top-1 agreement rate, cosine similarity</li>
        </ul>
        <div style={tip}>
          Use model_diff after merging to understand what changed. High KL divergence at specific
          positions shows where the merge had the biggest impact.
        </div>
      </div>

      {/* 6.5 Significance Report */}
      <SectionAnchor id="results-analysis/significance" title="Significance Report" level={2}>
        <TestTube size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> After running an <span style={code}>ab_significance</span> block,
          Results displays the statistical comparison.
        </p>
        <ul style={stepList}>
          <li>Two-column layout: Branch A stats vs Branch B stats (n, mean, std)</li>
          <li>
            p-value with color coding (<span style={{ color: '#22c55e' }}>green</span> = significant,{' '}
            <span style={{ color: '#6b7280' }}>gray</span> = not significant)
          </li>
          <li>Cohen&apos;s d with effect size label (negligible, small, medium, large)</li>
          <li>95% confidence interval as horizontal error bar</li>
          <li>Verdict text: &ldquo;Branch A is significantly better&rdquo; or &ldquo;No significant difference&rdquo;</li>
        </ul>
      </div>

      {/* 6.6 Run Comparison & Data Provenance */}
      <SectionAnchor
        id="results-analysis/provenance"
        title="Run Comparison & Data Provenance"
        level={2}
      >
        <History size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Tools for reproducibility — compare runs and track exactly which
          data produced which results.
        </p>
        <ul style={stepList}>
          <li>Compare any two runs: config diff shows which parameters changed</li>
          <li>Data provenance: each run records SHA256 hashes of all input datasets</li>
          <li>
            <span style={code}>GET /runs/&#123;id&#125;/data-provenance</span> — shows which exact
            data was used
          </li>
          <li>
            <span style={code}>POST /runs/compare-data</span> — compare data between two runs
          </li>
        </ul>
        <div style={tip}>
          Dataset hashing ensures you always know exactly which data produced which results —
          critical for reproducibility.
        </div>
      </div>

      {/* 6.7 Structured Export */}
      <SectionAnchor id="results-analysis/structured-export" title="Structured Export" level={2}>
        <FileJson size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Every completed run auto-generates a{' '}
          <span style={code}>run-export.json</span> file — the standard format that export
          connectors and external tools consume.
        </p>
        <ul style={stepList}>
          <li>Contains: run metadata, pipeline config, metrics (summary + timeseries), artifacts list, data provenance, environment info</li>
          <li>
            Download via: <span style={code}>GET /runs/&#123;id&#125;/export/download</span>
          </li>
          <li>
            This is the &ldquo;lingua franca&rdquo; that W&B, HuggingFace Hub, and Jupyter
            export connectors all consume
          </li>
        </ul>
      </div>
    </div>
  )
}
