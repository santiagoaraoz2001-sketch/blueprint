import { useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useHardwareStore } from '@/stores/hardwareStore'
import { useSettingsStore } from '@/stores/settingsStore'
import {
  estimatePipeline,
  formatTime,
  formatTimeShort,
  type HardwareSpec,
  type PipelineEstimate,
  type BlockEstimate,
} from '@/lib/pipeline-estimator'
import {
  Gauge,
  X,
  Clock,
  HardDrive,
  Cpu,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'

/* ------------------------------------------------------------------ */
/*  Styles                                                             */
/* ------------------------------------------------------------------ */

const labelStyle: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.xxs,
  fontWeight: 900,
  color: T.dim,
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
}

const valueStyle: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.lg,
  fontWeight: 700,
  letterSpacing: '0.02em',
}

const cardStyle: React.CSSProperties = {
  padding: '10px 12px',
  background: T.surface2,
  border: `1px solid ${T.border}`,
  borderRadius: 6,
}

/* ------------------------------------------------------------------ */
/*  Stat Card                                                          */
/* ------------------------------------------------------------------ */

function StatCard({
  icon: Icon,
  label,
  value,
  color,
  sub,
}: {
  icon: any
  label: string
  value: string
  color: string
  sub?: string
}) {
  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <Icon size={11} color={color} />
        <span style={labelStyle}>{label}</span>
      </div>
      <div style={{ ...valueStyle, color }}>{value}</div>
      {sub && (
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2, display: 'block' }}>
          {sub}
        </span>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Block Row                                                          */
/* ------------------------------------------------------------------ */

function BlockRow({ est, maxSeconds }: { est: BlockEstimate; maxSeconds: number }) {
  const barWidth = maxSeconds > 0 ? Math.max(2, (est.seconds / maxSeconds) * 100) : 0
  const hasWarnings = est.warnings.length > 0

  return (
    <div style={{ padding: '6px 0', borderBottom: `1px solid ${T.border}08` }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, minWidth: 0 }}>
          {hasWarnings && <AlertTriangle size={9} color={T.amber} />}
          <span style={{
            fontFamily: F,
            fontSize: FS.xs,
            color: hasWarnings ? T.amber : T.sec,
            fontWeight: 600,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {est.label}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            {est.memoryGB.toFixed(1)} GB
          </span>
          <span style={{
            fontFamily: F,
            fontSize: FS.xs,
            color: T.text,
            fontWeight: 700,
            minWidth: 48,
            textAlign: 'right',
          }}>
            {formatTimeShort(est.seconds)}
          </span>
        </div>
      </div>
      {/* Time bar */}
      <div style={{ height: 3, background: T.surface3, borderRadius: 2, overflow: 'hidden' }}>
        <div style={{
          height: '100%',
          width: `${barWidth}%`,
          background: hasWarnings
            ? `linear-gradient(90deg, ${T.amber}, ${T.amber}80)`
            : `linear-gradient(90deg, ${T.cyan}, ${T.cyan}60)`,
          borderRadius: 2,
          transition: 'width 0.3s ease',
        }} />
      </div>
      {/* Warning messages */}
      {est.warnings.map((w, i) => (
        <div key={i} style={{
          display: 'flex', alignItems: 'center', gap: 4,
          marginTop: 3,
          fontFamily: F, fontSize: FS.xxs, color: T.amber, lineHeight: 1.4,
        }}>
          <span style={{ opacity: 0.7 }}>•</span> {w}
        </div>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main Panel                                                         */
/* ------------------------------------------------------------------ */

export default function PipelineAnalysisPanel({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const nodes = usePipelineStore((s) => s.nodes)
  const profile = useHardwareStore((s) => s.profile)
  const settingsHw = useSettingsStore((s) => s.hardware)
  const [expanded, setExpanded] = useState(true)

  // Build hardware spec — prefer hardwareStore, fall back to settingsStore
  const hw: HardwareSpec | undefined = useMemo(() => {
    if (profile) {
      return {
        ramGB: profile.ram.total_gb,
        gpuVramGB: profile.gpu[0]?.vram_gb ?? 0,
        gpuType: (profile.gpu[0]?.type as HardwareSpec['gpuType']) ?? 'cpu',
        cpuCores: profile.cpu.cores,
      }
    }
    if (settingsHw) {
      return {
        ramGB: settingsHw.usable_memory_gb || 18,
        gpuVramGB: settingsHw.max_vram_gb || 0,
        gpuType: settingsHw.gpu_backend === 'metal' ? 'metal'
          : settingsHw.gpu_backend === 'cuda' ? 'cuda'
          : settingsHw.gpu_available ? 'metal' : 'cpu',
        cpuCores: 10,
      }
    }
    return undefined
  }, [profile, settingsHw])

  const estimate: PipelineEstimate = useMemo(
    () => estimatePipeline(nodes, hw),
    [nodes, hw],
  )

  const maxBlockSeconds = Math.max(...estimate.blockEstimates.map(b => b.seconds), 1)
  const gpuBlocks = estimate.blockEstimates.filter(b => b.gpuRequired).length
  const warningCount = estimate.blockEstimates.reduce((n, b) => n + b.warnings.length, 0) + estimate.warnings.length

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0, x: 300 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 300 }}
          transition={{ type: 'spring', damping: 26, stiffness: 300 }}
          style={{
            position: 'fixed',
            top: 52,
            right: 0,
            bottom: 28,
            width: 380,
            background: T.surface1,
            borderLeft: `1px solid ${T.borderHi}`,
            boxShadow: `0 0 40px ${T.shadowHeavy}`,
            zIndex: 1100,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Header */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 16px',
            borderBottom: `1px solid ${T.border}`,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Gauge size={14} color={T.amber} />
              <span style={{
                fontFamily: F,
                fontSize: FS.sm,
                fontWeight: 900,
                color: T.text,
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
              }}>
                Pipeline Analysis
              </span>
            </div>
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                color: T.dim,
                cursor: 'pointer',
                padding: 4,
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <X size={14} />
            </button>
          </div>

          {/* Scrollable content */}
          <div style={{ flex: 1, overflowY: 'auto', padding: 16, scrollbarWidth: 'thin' }}>
            {/* Summary stats */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
              <StatCard
                icon={Clock}
                label="Total Time"
                value={formatTime(estimate.totalSeconds)}
                color={T.cyan}
                sub={`${estimate.blockEstimates.length} blocks`}
              />
              <StatCard
                icon={HardDrive}
                label="Peak Memory"
                value={`${estimate.peakMemoryGB.toFixed(1)} GB`}
                color={estimate.feasible ? T.green : T.red}
                sub={hw ? `of ${hw.ramGB} GB` : 'unknown hardware'}
              />
            </div>

            {/* Feasibility badge */}
            <div style={{
              ...cardStyle,
              marginBottom: 16,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              borderColor: estimate.feasible ? `${T.green}40` : `${T.red}40`,
              background: estimate.feasible ? `${T.green}08` : `${T.red}08`,
            }}>
              {estimate.feasible
                ? <CheckCircle2 size={14} color={T.green} />
                : <AlertTriangle size={14} color={T.red} />
              }
              <div>
                <div style={{
                  fontFamily: F,
                  fontSize: FS.xs,
                  fontWeight: 900,
                  color: estimate.feasible ? T.green : T.red,
                  letterSpacing: '0.08em',
                }}>
                  {estimate.feasible ? 'FEASIBLE' : 'EXCEEDS CAPACITY'}
                </div>
                <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>
                  {gpuBlocks} GPU block{gpuBlocks !== 1 ? 's' : ''}
                  {warningCount > 0 && ` · ${warningCount} warning${warningCount !== 1 ? 's' : ''}`}
                </div>
              </div>
            </div>

            {/* Global warnings */}
            {estimate.warnings.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                {estimate.warnings.map((w, i) => (
                  <div key={i} style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 6,
                    padding: '6px 10px',
                    background: `${T.amber}0a`,
                    border: `1px solid ${T.amber}20`,
                    borderRadius: 4,
                    marginBottom: 4,
                  }}>
                    <AlertTriangle size={10} color={T.amber} style={{ marginTop: 2, flexShrink: 0 }} />
                    <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.amber, lineHeight: 1.5 }}>
                      {w}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Hardware info */}
            <div style={{ ...cardStyle, marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <Cpu size={11} color={T.sec} />
                <span style={labelStyle}>HARDWARE</span>
              </div>
              <div style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, lineHeight: 1.7 }}>
                {hw ? (
                  <>
                    {profile?.cpu.brand || settingsHw?.gpu_backend?.toUpperCase() || 'Detected'} · {hw.cpuCores} cores
                    <br />
                    {hw.ramGB} GB RAM · {hw.gpuType.toUpperCase()}
                    {hw.gpuVramGB > 0 && ` · ${hw.gpuVramGB} GB VRAM`}
                  </>
                ) : (
                  <>
                    No hardware detected — using reference estimates
                    <br />
                    <span style={{ color: T.dim }}>
                      (M3 Pro · 10 cores · 36 GB · Metal)
                    </span>
                  </>
                )}
              </div>
            </div>

            {/* Per-block breakdown */}
            <div>
              <button
                onClick={() => setExpanded(e => !e)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: '4px 0',
                  marginBottom: 8,
                }}
              >
                {expanded
                  ? <ChevronDown size={12} color={T.dim} />
                  : <ChevronRight size={12} color={T.dim} />
                }
                <span style={labelStyle}>PER-BLOCK BREAKDOWN</span>
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                  ({estimate.blockEstimates.length})
                </span>
              </button>

              {expanded && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                >
                  {estimate.blockEstimates.length === 0 ? (
                    <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, padding: '12px 0', textAlign: 'center' }}>
                      Add blocks to see estimates
                    </div>
                  ) : (
                    estimate.blockEstimates
                      .sort((a, b) => b.seconds - a.seconds)
                      .map((est) => (
                        <BlockRow key={est.nodeId} est={est} maxSeconds={maxBlockSeconds} />
                      ))
                  )}
                </motion.div>
              )}
            </div>
          </div>

          {/* Footer */}
          <div style={{
            padding: '10px 16px',
            borderTop: `1px solid ${T.border}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              Estimates based on {hw?.gpuType === 'metal' ? 'Apple Silicon' : hw?.gpuType?.toUpperCase() || 'reference'} hardware
            </span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
