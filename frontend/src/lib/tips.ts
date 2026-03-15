export interface GuideTip {
  id: string
  label: string
  description: string
  level: 'dash' | 'deep' | 'learn'
}

export type ViewId = 'dashboard' | 'editor' | 'results' | 'datasets' | 'marketplace'

export const VIEW_TIPS: Record<ViewId, GuideTip[]> = {
  dashboard: [
    { id: 'dash-projects', label: 'PROJECTS', description: 'Create projects to organize related experiments, pipelines, and results. Each project tracks paper numbers and GitHub repos.', level: 'dash' },
    { id: 'dash-experiments', label: 'EXPERIMENTS', description: 'Group related pipeline runs into experiments for systematic comparison and analysis.', level: 'dash' },
    { id: 'dash-status', label: 'STATUS TRACKING', description: 'Projects flow through planning → active → complete. Track progress at a glance from the dashboard cards.', level: 'deep' },
  ],
  editor: [
    { id: 'ed-blocks', label: 'BLOCK LIBRARY', description: 'Drag blocks from the library panel on the left onto the canvas to build your pipeline. 100+ blocks across 11 categories.', level: 'dash' },
    { id: 'ed-ports', label: 'PORT COLORS', description: 'Each color represents a data type: green=dataset, pink=text, violet=model, cyan=config, amber=metrics, teal=embedding, red=artifact, sky=agent, gold=llm, gray=any. Match colors for compatible connections.', level: 'dash' },
    { id: 'ed-connect', label: 'CONNECTIONS', description: 'Drag from an output handle (bottom) to an input handle (top) to connect blocks. Mismatched types will be rejected.', level: 'dash' },
    { id: 'ed-config', label: 'CONFIGURATION', description: 'Click a block to open its config panel on the right. Each block has type-specific parameters.', level: 'deep' },
    { id: 'ed-run', label: 'EXECUTION', description: 'Click Run to execute the pipeline. Blocks execute in topological order with real-time progress tracking.', level: 'deep' },
    { id: 'ed-save', label: 'AUTO-SAVE', description: 'Pipelines auto-save when modified. Use Cmd+S for manual save.', level: 'learn' },
  ],
  results: [
    { id: 'res-table', label: 'RESULTS TABLE', description: 'View all run results with sortable columns. Click column headers to sort by any metric.', level: 'dash' },
    { id: 'res-chart', label: 'METRIC CHARTS', description: 'Switch to Chart view to visualize metrics over time. Select X and Y axes from any config parameter or metric.', level: 'dash' },
    { id: 'res-compare', label: 'COMPARISON', description: 'Select 2-4 runs to compare side-by-side with config diffs and metric deltas highlighted.', level: 'deep' },
  ],
  datasets: [
    { id: 'ds-register', label: 'REGISTER DATASETS', description: 'Register local files (CSV, JSONL, Parquet) to make them available in pipeline blocks.', level: 'dash' },
    { id: 'ds-preview', label: 'PREVIEW', description: 'Click a dataset to preview its columns, sample rows, and basic statistics.', level: 'dash' },
    { id: 'ds-version', label: 'VERSIONING', description: 'Datasets are versioned automatically. Track changes and rollback when needed.', level: 'deep' },
  ],
  marketplace: [
    { id: 'mk-browse', label: 'BLOCK LIBRARY', description: 'Browse all available blocks organized by category. Each block card shows inputs, outputs, and descriptions.', level: 'dash' },
    { id: 'mk-custom', label: 'CUSTOM BLOCKS', description: 'Create your own blocks with a block.yaml config and run.py script. Use the Block SDK for full control.', level: 'deep' },
    { id: 'mk-share', label: 'SHARING', description: 'Export and share custom blocks with your team or the community.', level: 'learn' },
  ],
}
