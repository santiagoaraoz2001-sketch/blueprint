import { T } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import { Activity, Cpu, Wifi, FileText } from 'lucide-react'
import { helpCard as card, helpBody as body, helpTip as tip, helpStepList as stepList, helpCode as code } from './styles'

export const EXECUTION_MONITORING_TEXT = `Execution Engine. Pipelines execute as a DAG in topological order. Each block receives outputs from upstream via BlockContext. Outputs are persisted after each block (partial outputs survive crashes). JSONL + SQLite dual-write for metrics. Heartbeat every 30 seconds during long blocks. Stale runs (no heartbeat for 5 min) auto-recover to failed status. Circuit Breaker: The API client includes a circuit breaker that prevents retry storms when the backend is unavailable, automatically backing off and recovering. Memory Pressure Monitoring: Blueprint monitors system memory and triggers automatic cleanup of zombie processes when pressure is high, preventing OOM crashes. Artifact Registry: All block outputs are tracked in a global artifact registry, browsable from the Outputs Monitor. Monitor View. Real-time dashboard during pipeline execution. Shows current block, progress bars, ETA, elapsed time, live logs, system metrics (CPU, memory, GPU). Control Tower provides live heartbeat tracking across all active runs. Specialized dashboards per category: Training (loss curves), Evaluation (benchmark bars), Inference (latency), Merge (progress), Data (row counts). Plugin Panels: Plugins can inject custom panels. SSE Connection. Blueprint uses Server-Sent Events for real-time updates. Single connection per run. Auto-reconnects with exponential backoff (up to 10 attempts). lastEventId replay on reconnect. Status badge: green (Live), yellow (Reconnecting), red (Connection lost), gray (Disconnected). 15-second keepalive prevents proxy/NAT timeouts. Structured Logging. All executor events logged as JSON lines to ~/.specific-labs/logs/blueprint.jsonl. Events: run_start, block_start, block_complete, block_failed, run_complete, run_failed, stale_recovery, config_resolved. Log rotation at 50MB, 5 backups. Diagnostics endpoint: GET /api/system/diagnostics/{run_id}.`

export default function ExecutionMonitoring() {
  return (
    <div>
      <SectionAnchor id="execution-monitoring" title="Execution & Monitoring" level={1}>
        <Activity size={22} color={T.cyan} />
      </SectionAnchor>

      {/* 5.1 Execution Engine */}
      <SectionAnchor id="execution-monitoring/engine" title="Execution Engine" level={2}>
        <Cpu size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Pipelines execute as a DAG (Directed Acyclic Graph) in topological
          order. Each block receives outputs from upstream blocks via the BlockContext.
        </p>
        <ul style={stepList}>
          <li>Outputs are persisted after each block — partial outputs survive crashes</li>
          <li>JSONL + SQLite dual-write for metrics (JSONL is the crash-safe fallback)</li>
          <li>Heartbeat every 30 seconds during long blocks</li>
          <li>
            Stale runs (no heartbeat for 5 min) auto-recover to &ldquo;failed&rdquo; status with a
            stale_recovery event logged
          </li>
          <li>
            <strong>Circuit breaker:</strong> The API client prevents retry storms when the backend is
            unavailable — automatically backs off and recovers when the server returns
          </li>
          <li>
            <strong>Memory pressure monitoring:</strong> Blueprint monitors system memory and
            automatically cleans up zombie processes when memory pressure is high, preventing OOM crashes
          </li>
          <li>
            <strong>Artifact registry:</strong> All block outputs are tracked in a global artifact
            registry, browsable from the Outputs Monitor view
          </li>
        </ul>
        <div style={tip}>
          Because outputs persist after each block, if a pipeline fails at step 5 of 8, you don&apos;t
          lose the outputs from steps 1–4. Use &ldquo;Re-run from here&rdquo; to resume.
        </div>
      </div>

      {/* 5.2 Monitor View */}
      <SectionAnchor id="execution-monitoring/monitor" title="Monitor View" level={2}>
        <Activity size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> A real-time dashboard that shows everything happening during
          pipeline execution.
        </p>
        <ul style={stepList}>
          <li>Shows: current block, progress bars, ETA, elapsed time, live logs</li>
          <li>System metrics: CPU, memory, GPU utilization</li>
          <li>
            <strong>Control Tower:</strong> A live dashboard showing all active runs with heartbeat
            tracking, status, and elapsed time across the entire workspace
          </li>
          <li>
            Specialized dashboards per category:
            <ul style={{ paddingLeft: 16, marginTop: 4 }}>
              <li>Training → loss curves (updating live)</li>
              <li>Evaluation → benchmark bar charts</li>
              <li>Inference → latency distribution</li>
              <li>Merge → merge progress percentage</li>
              <li>Data → row counts and processing speed</li>
            </ul>
          </li>
          <li>
            <strong>Plugin Panels:</strong> Plugins can inject custom panels into the Monitor view
            (e.g., W&B metrics panel). Panels are drag-and-drop, resizable, and configurable.
            Without plugins, shows a &ldquo;Browse Plugins&rdquo; callout.
          </li>
        </ul>
      </div>

      {/* 5.3 SSE Connection */}
      <SectionAnchor id="execution-monitoring/sse" title="SSE Connection" level={2}>
        <Wifi size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> Blueprint uses Server-Sent Events (SSE) for real-time updates
          between the backend and the UI.
        </p>
        <ul style={stepList}>
          <li>Single connection per run (unified across all UI components)</li>
          <li>Auto-reconnects with exponential backoff (up to 10 attempts)</li>
          <li>
            <span style={code}>lastEventId</span> replay on reconnect — no missed events
          </li>
          <li>
            Status badge:{' '}
            <span style={{ color: '#22c55e' }}>green</span> (Live),{' '}
            <span style={{ color: '#eab308' }}>yellow</span> (Reconnecting),{' '}
            <span style={{ color: '#ef4444' }}>red</span> (Connection lost),{' '}
            <span style={{ color: '#6b7280' }}>gray</span> (Disconnected)
          </li>
          <li>15-second keepalive prevents proxy/NAT timeouts</li>
        </ul>
        <div style={tip}>
          If you&apos;re behind a reverse proxy, configure its timeout to be greater than 20 seconds to
          avoid SSE drops.
        </div>
      </div>

      {/* 5.4 Structured Logging */}
      <SectionAnchor id="execution-monitoring/logging" title="Structured Logging" level={2}>
        <FileText size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>What:</strong> All executor events are logged as JSON lines for debugging and
          auditability.
        </p>
        <ul style={stepList}>
          <li>
            Log file: <span style={code}>~/.specific-labs/logs/blueprint.jsonl</span>
          </li>
          <li>
            Events: <span style={code}>run_start</span>, <span style={code}>block_start</span>,{' '}
            <span style={code}>block_complete</span>, <span style={code}>block_failed</span>,{' '}
            <span style={code}>run_complete</span>, <span style={code}>run_failed</span>,{' '}
            <span style={code}>stale_recovery</span>, <span style={code}>config_resolved</span>
          </li>
          <li>Log rotation at 50MB with 5 backups</li>
          <li>
            Diagnostics endpoint:{' '}
            <span style={code}>GET /api/system/diagnostics/&#123;run_id&#125;</span> returns a
            timeline of events for any run
          </li>
        </ul>
        <div style={tip}>
          Use the diagnostics endpoint to debug slow or failed runs. It shows a timeline of every
          event with timestamps and durations.
        </div>
      </div>
    </div>
  )
}
