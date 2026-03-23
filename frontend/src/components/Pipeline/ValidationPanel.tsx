import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle2, XCircle, AlertTriangle, X, ChevronDown, ChevronRight, Info, Cpu, Zap, Settings2, Link2, LayoutList } from 'lucide-react'
import { useReactFlow } from '@xyflow/react'
import { usePipelineStore } from '@/stores/pipelineStore'
import type { DiagnosticReport, DiagnosticItem, ReportSection } from '@/lib/pipeline-validator'
import { formatTime } from '@/lib/pipeline-estimator'

interface ValidationPanelProps {
  visible: boolean
  report: DiagnosticReport | null
  onClose: () => void
}

const SECTION_ICONS: Record<string, typeof Cpu> = {
  Structure: LayoutList,
  Configuration: Settings2,
  Compatibility: Link2,
  Hardware: Cpu,
  Performance: Zap,
}

function scoreColor(score: number): string {
  if (score >= 80) return T.green
  if (score >= 50) return T.amber
  return T.red
}

export default function ValidationPanel({ visible, report, onClose }: ValidationPanelProps) {
  const { fitView } = useReactFlow()
  const focusErrorNode = usePipelineStore((s) => s.focusErrorNode)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  const handleItemClick = (item: DiagnosticItem) => {
    if (!item.nodeId) return
    focusErrorNode(item.nodeId)
    fitView({ nodes: [{ id: item.nodeId }], duration: 800, padding: 0.5 })
  }

  const toggleSection = (title: string) => {
    setCollapsed(s => ({ ...s, [title]: !s[title] }))
  }

  return (
    <AnimatePresence>
      {visible && report && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={onClose}
            style={{ position: 'fixed', inset: 0, background: T.shadow, zIndex: 200 }}
          />

          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            style={{
              position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
              width: 480, maxHeight: '85vh', background: T.surface2,
              border: `1px solid ${T.borderHi}`, boxShadow: `0 16px 48px ${T.shadowHeavy}`,
              zIndex: 201, display: 'flex', flexDirection: 'column', overflow: 'hidden',
            }}
          >
            {/* ── Header ── */}
            <div style={{ display: 'flex', alignItems: 'center', padding: '10px 14px', borderBottom: `1px solid ${T.border}`, gap: 8 }}>
              {report.valid ? <CheckCircle2 size={16} color={T.green} /> : <XCircle size={16} color={T.red} />}
              <span style={{ fontFamily: F, fontSize: FS.md, fontWeight: 700, color: report.valid ? T.green : T.red, letterSpacing: '0.08em', flex: 1 }}>
                {report.valid ? 'PIPELINE READY' : 'ISSUES FOUND'}
              </span>
              {/* Health Score Badge */}
              <div style={{
                padding: '2px 8px', borderRadius: 10,
                background: `${scoreColor(report.score)}20`,
                border: `1px solid ${scoreColor(report.score)}40`,
              }}>
                <span style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: scoreColor(report.score) }}>
                  {report.score}
                </span>
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginLeft: 2 }}>/100</span>
              </div>
              <button onClick={onClose} style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2, display: 'flex' }}>
                <X size={14} />
              </button>
            </div>

            {/* ── Content ── */}
            <div style={{ overflowY: 'auto', padding: '8px 14px' }}>
              {/* Stats row */}
              <div style={{ display: 'flex', gap: 12, padding: '6px 0', marginBottom: 8, borderBottom: `1px solid ${T.border}`, flexWrap: 'wrap' }}>
                <StatItem label="BLOCKS" value={String(report.stats.blockCount)} />
                <StatItem label="EDGES" value={String(report.stats.edgeCount)} />
                <StatItem label="RUNTIME" value={formatTime(report.stats.estimatedRuntime)} />
                <StatItem label="PEAK MEM" value={`${report.stats.peakMemoryGB.toFixed(1)} GB`} />
                <StatItem label="GPU" value={report.stats.gpuRequired ? 'Required' : 'No'} color={report.stats.gpuRequired ? T.amber : T.green} />
              </div>

              {/* Hardware summary */}
              <div style={{ padding: '6px 8px', marginBottom: 8, background: `${T.surface3}`, border: `1px solid ${T.border}`, borderRadius: 4 }}>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  <MiniStat label="RAM" value={`${report.hardware.ramAvailableGB} GB`} />
                  <MiniStat label="VRAM" value={`${report.hardware.gpuVramGB} GB`} />
                  <MiniStat label="GPU" value={report.hardware.gpuType.toUpperCase()} />
                  <MiniStat
                    label="HW STATUS"
                    value={report.hardware.feasible ? 'OK' : 'INFEASIBLE'}
                    color={report.hardware.feasible ? T.green : T.red}
                  />
                </div>
                {report.hardware.recommendations.length > 0 && (
                  <div style={{ marginTop: 4, paddingTop: 4, borderTop: `1px solid ${T.border}` }}>
                    {report.hardware.recommendations.map((rec, i) => (
                      <div key={i} style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, lineHeight: 1.6 }}>
                        {rec}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Sections */}
              {report.sections.map((section) => (
                <SectionCard
                  key={section.title}
                  section={section}
                  collapsed={!!collapsed[section.title]}
                  onToggle={() => toggleSection(section.title)}
                  onItemClick={handleItemClick}
                />
              ))}

              {/* All clear */}
              {report.valid && report.errors.length === 0 && report.warnings.length === 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 0' }}>
                  <CheckCircle2 size={14} color={T.green} />
                  <span style={{ fontFamily: F, fontSize: FS.sm, color: T.green }}>
                    Pipeline is valid and ready to run.
                  </span>
                </div>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

function SectionCard({ section, collapsed, onToggle, onItemClick }: {
  section: ReportSection
  collapsed: boolean
  onToggle: () => void
  onItemClick: (item: DiagnosticItem) => void
}) {
  const statusColor = section.status === 'fail' ? T.red : section.status === 'warn' ? T.amber : T.green
  const StatusIcon = section.status === 'fail' ? XCircle : section.status === 'warn' ? AlertTriangle : CheckCircle2
  const SectionIcon = SECTION_ICONS[section.title] || Info
  const Chevron = collapsed ? ChevronRight : ChevronDown

  if (section.items.length === 0) return null

  return (
    <div style={{ marginBottom: 6, border: `1px solid ${T.border}`, borderRadius: 4, overflow: 'hidden' }}>
      <button
        onClick={onToggle}
        style={{
          display: 'flex', alignItems: 'center', gap: 6, width: '100%', padding: '6px 8px',
          background: `${statusColor}08`, border: 'none', cursor: 'pointer', textAlign: 'left',
        }}
      >
        <SectionIcon size={11} color={statusColor} style={{ flexShrink: 0 }} />
        <span style={{ fontFamily: F, fontSize: FS.xs, fontWeight: 700, color: statusColor, letterSpacing: '0.08em', flex: 1 }}>
          {section.title.toUpperCase()}
        </span>
        <StatusIcon size={10} color={statusColor} />
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{section.items.length}</span>
        <Chevron size={10} color={T.dim} />
      </button>
      {!collapsed && (
        <div style={{ padding: '4px 8px 6px' }}>
          {section.items.map((item, i) => (
            <ItemRow key={i} item={item} onClick={() => onItemClick(item)} />
          ))}
        </div>
      )}
    </div>
  )
}

function ItemRow({ item, onClick }: { item: DiagnosticItem; onClick: () => void }) {
  const color = item.severity === 'error' ? T.red : item.severity === 'warning' ? T.amber : T.sec
  const Icon = item.severity === 'error' ? XCircle : item.severity === 'warning' ? AlertTriangle : Info

  return (
    <div
      onClick={item.nodeId ? onClick : undefined}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 6, padding: '4px 4px',
        borderRadius: 3, cursor: item.nodeId ? 'pointer' : 'default',
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => { if (item.nodeId) e.currentTarget.style.background = `${color}10` }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
    >
      <Icon size={10} color={color} style={{ flexShrink: 0, marginTop: 2 }} />
      <div style={{ flex: 1 }}>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color, lineHeight: 1.5 }}>
          {item.message}
        </span>
        {item.suggestion && (
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, lineHeight: 1.4, marginTop: 1, fontStyle: 'italic' }}>
            {item.suggestion}
          </div>
        )}
        {item.nodeId && (
          <span style={{ fontFamily: F, fontSize: 5.5, color: T.dim, marginLeft: 4, textDecoration: 'underline' }}>
            Focus
          </span>
        )}
      </div>
    </div>
  )
}

function StatItem({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.08em', marginBottom: 1 }}>{label}</div>
      <div style={{ fontFamily: F, fontSize: FS.sm, color: color ?? T.text, fontWeight: 600 }}>{value}</div>
    </div>
  )
}

function MiniStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'baseline' }}>
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.05em' }}>{label}</span>
      <span style={{ fontFamily: F, fontSize: FS.xs, color: color ?? T.sec, fontWeight: 600 }}>{value}</span>
    </div>
  )
}
