import { T, F, FS } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import { Layout, FolderPlus, RefreshCw, FileQuestion } from 'lucide-react'
import { helpCard as card, helpBody as body, helpTip as tip, helpStepList as stepList } from './styles'

export const PROJECTS_DASHBOARD_TEXT = `Creating Projects. Projects group related experiments. Each has a name, description, and hypothesis. Click NEW PROJECT on the Dashboard. The active project filters all other views. Project Lifecycle. Projects have phases (data collection, training, evaluation, publication). Phases auto-complete when completed_runs >= total_runs. Dashboard shows aggregate stats: total runs, success rate, active pipelines. Unassigned Runs. Runs can exist without a phase assignment. Use POST /runs/{id}/assign for retroactive linking.`

export default function ProjectsDashboard() {
  return (
    <div>
      <SectionAnchor id="projects-dashboard" title="Projects & Dashboard" level={1}>
        <Layout size={22} color={T.accent} />
      </SectionAnchor>

      {/* 2.1 Creating Projects */}
      <SectionAnchor id="projects-dashboard/creating" title="Creating Projects" level={2}>
        <FolderPlus size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Projects group related experiments, each with a name, description,
          and hypothesis.
        </p>
        <p style={{ ...body, marginTop: 8 }}>
          <strong>How:</strong> Click &ldquo;NEW PROJECT&rdquo; on the Dashboard. Fill in the project
          name and description. The active project filters all other views (Pipeline Editor, Results,
          Datasets, etc.).
        </p>
        <p style={{ ...body, marginTop: 8 }}>
          <strong>Why:</strong> Organize experiments by research question. Each project is an
          isolated workspace so different experiments don&apos;t interfere.
        </p>
        <div style={tip}>Click a project card to select it — all other views will filter to that project.</div>
      </div>

      {/* 2.2 Project Lifecycle */}
      <SectionAnchor id="projects-dashboard/lifecycle" title="Project Lifecycle" level={2}>
        <RefreshCw size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Projects have phases — data collection, training, evaluation, and
          publication — that track progress automatically.
        </p>
        <ul style={stepList}>
          <li>Phases auto-complete when completed runs meet the target count</li>
          <li>Dashboard shows aggregate stats: total runs, success rate, active pipelines</li>
          <li>Project overview shows recent runs and quick stats at a glance</li>
        </ul>
        <div style={tip}>
          Use phases to track your experiment workflow from data prep through publication. Phases
          update automatically as pipeline runs complete.
        </div>
      </div>

      {/* 2.3 Unassigned Runs */}
      <SectionAnchor id="projects-dashboard/unassigned-runs" title="Unassigned Runs" level={2}>
        <FileQuestion size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Runs can exist without a phase assignment, useful for exploratory
          experiments.
        </p>
        <p style={{ ...body, marginTop: 8 }}>
          <strong>How:</strong> Runs created outside of a phase appear in the &ldquo;Unassigned&rdquo;
          section. Use the API endpoint{' '}
          <span
            style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: FS.xs,
              background: T.surface1,
              padding: '2px 6px',
              color: T.accent,
            }}
          >
            POST /runs/&#123;id&#125;/assign
          </span>{' '}
          for retroactive linking to a phase.
        </p>
        <div style={tip}>
          Unassigned runs are still tracked in Results and can be compared with assigned runs.
        </div>
      </div>
    </div>
  )
}
