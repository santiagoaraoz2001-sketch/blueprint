import { useState, useMemo } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import {
  BLOCK_REGISTRY,
  type BlockDefinition,
  type PortDefinition,
  getPortColor,
  isPortCompatible,
} from '@/lib/block-registry'
import { getAdvancedConfig } from '@/lib/advanced-configs'
import { getIcon } from '@/lib/icon-utils'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useUIStore } from '@/stores/uiStore'
import { motion } from 'framer-motion'
import {
  ArrowLeft,
  ArrowDown,
  Lightbulb,
  Code,
  ChevronDown,
  ChevronRight,
  Zap,
  Layers,
  Settings,
  PlusCircle,
} from 'lucide-react'
import toast from 'react-hot-toast'

interface BlockDetailPageProps {
  block: BlockDefinition
  onBack: () => void
  onSelectBlock?: (block: BlockDefinition) => void
}

export default function BlockDetailPage({ block, onBack, onSelectBlock }: BlockDetailPageProps) {
  const [showAdvanced, setShowAdvanced] = useState(false)

  const IconComponent = getIcon(block.icon)
  const accent = block.accent || T.cyan
  const advancedConfig = getAdvancedConfig(block.type)

  // Find compatible blocks
  const compatibleBlocks = useMemo(() => {
    const compatible: { block: BlockDefinition; direction: 'input' | 'output'; portLabel: string }[] = []
    const seen = new Set<string>()

    for (const other of BLOCK_REGISTRY) {
      if (other.type === block.type) continue

      // Can this block's outputs connect to other's inputs?
      for (const myOut of block.outputs) {
        for (const theirIn of other.inputs) {
          if (isPortCompatible(myOut.dataType, theirIn.dataType) && !seen.has(`out-${other.type}`)) {
            compatible.push({ block: other, direction: 'output', portLabel: `${myOut.label} -> ${theirIn.label}` })
            seen.add(`out-${other.type}`)
          }
        }
      }

      // Can other's outputs connect to this block's inputs?
      for (const theirOut of other.outputs) {
        for (const myIn of block.inputs) {
          if (isPortCompatible(theirOut.dataType, myIn.dataType) && !seen.has(`in-${other.type}`)) {
            compatible.push({ block: other, direction: 'input', portLabel: `${theirOut.label} -> ${myIn.label}` })
            seen.add(`in-${other.type}`)
          }
        }
      }
    }

    return compatible.slice(0, 12) // Limit to 12 for UI
  }, [block])

  // Group config fields by depends_on
  const configGroups = useMemo(() => {
    const groups: { label: string; fields: typeof block.configFields }[] = []
    const ungrouped: typeof block.configFields = []
    const dependentGroups: Record<string, typeof block.configFields> = {}

    for (const field of block.configFields) {
      if (field.depends_on) {
        const key = `${field.depends_on.field}=${field.depends_on.value}`
        if (!dependentGroups[key]) dependentGroups[key] = []
        dependentGroups[key].push(field)
      } else {
        ungrouped.push(field)
      }
    }

    if (ungrouped.length > 0) {
      groups.push({ label: 'General', fields: ungrouped })
    }
    for (const [key, fields] of Object.entries(dependentGroups)) {
      groups.push({ label: `When ${key}`, fields })
    }

    return groups
  }, [block.configFields])

  const handleAddToCanvas = () => {
    usePipelineStore.getState().addNode(block.type, { x: 400, y: 300 })
    useUIStore.getState().setView('editor')
    toast.success(`Added ${block.name} to canvas`)
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 40 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -40 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Back Navigation */}
      <button
        onClick={onBack}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '10px 20px',
          background: 'none',
          border: 'none',
          color: T.cyan,
          fontFamily: F,
          fontSize: FS.sm,
          fontWeight: 600,
          cursor: 'pointer',
          letterSpacing: '0.04em',
          flexShrink: 0,
          transition: 'color 0.15s',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = T.text)}
        onMouseLeave={(e) => (e.currentTarget.style.color = T.cyan)}
      >
        <ArrowLeft size={12} />
        Back to Library
      </button>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflow: 'auto', padding: '0 24px 24px' }}>
        {/* Hero Banner */}
        <div
          style={{
            background: `linear-gradient(180deg, ${T.surface2} 0%, ${T.surface0} 100%)`,
            border: `1px solid ${T.border}`,
            borderTop: `4px solid ${accent}`,
            borderRadius: '0 0 8px 8px',
            padding: '24px 28px',
            marginBottom: 24,
            backdropFilter: 'blur(12px)',
            boxShadow: `0 8px 32px ${T.shadow}, 0 0 60px ${accent}08`,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div
              style={{
                width: 52,
                height: 52,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: `${accent}14`,
                border: `1px solid ${accent}33`,
                borderRadius: 12,
                boxShadow: `0 0 24px ${accent}20`,
              }}
            >
              <IconComponent size={24} color={accent} />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <h2
                  style={{
                    margin: 0,
                    fontFamily: FD,
                    fontSize: FS.h2,
                    color: T.text,
                    fontWeight: 700,
                    letterSpacing: '0.02em',
                  }}
                >
                  {block.name}
                </h2>
                <span
                  style={{
                    padding: '2px 8px',
                    background: `${accent}15`,
                    border: `1px solid ${accent}30`,
                    borderRadius: 4,
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: accent,
                    fontWeight: 700,
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                  }}
                >
                  {block.category}
                </span>
                {block.maturity && block.maturity !== 'stable' && (
                  <span
                    style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: 4,
                      letterSpacing: '0.06em',
                      textTransform: 'uppercase',
                      ...(block.maturity === 'beta'
                        ? { color: '#F59E0B', background: '#F59E0B15', border: '1px solid #F59E0B30' }
                        : { color: '#8B5CF6', background: '#8B5CF615', border: '1px solid #8B5CF630' }),
                    }}
                  >
                    {block.maturity}
                  </span>
                )}
              </div>
              {/* Tags */}
              {block.tags && block.tags.length > 0 && (
                <div style={{ display: 'flex', gap: 5, marginTop: 8, flexWrap: 'wrap' }}>
                  {block.tags.map((tag) => (
                    <span
                      key={tag}
                      style={{
                        padding: '1px 7px',
                        background: T.surface3,
                        borderRadius: 10,
                        fontSize: FS.xxs,
                        fontFamily: F,
                        color: T.sec,
                        border: `1px solid ${T.border}`,
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Two-column layout */}
        <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
          {/* Main Column (65%) */}
          <div style={{ flex: '0 0 65%', maxWidth: '65%', display: 'flex', flexDirection: 'column', gap: 24 }}>
            {/* Description */}
            <Section title="DESCRIPTION">
              <p
                style={{
                  fontFamily: F,
                  fontSize: FS.sm,
                  color: T.sec,
                  lineHeight: 1.7,
                  margin: 0,
                }}
              >
                {block.description}
              </p>
            </Section>

            {/* How It Works */}
            {block.detail?.howItWorks && (
              <Section title="HOW IT WORKS">
                <p
                  style={{
                    fontFamily: F,
                    fontSize: FS.sm,
                    color: T.sec,
                    lineHeight: 1.7,
                    margin: 0,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {block.detail.howItWorks}
                </p>
              </Section>
            )}

            {/* Use Cases */}
            {block.detail?.useCases && block.detail.useCases.length > 0 && (
              <Section title="USE CASES">
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: 16,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                  }}
                >
                  {block.detail.useCases.map((uc, i) => (
                    <li
                      key={i}
                      style={{
                        fontFamily: F,
                        fontSize: FS.sm,
                        color: T.sec,
                        lineHeight: 1.6,
                      }}
                    >
                      {uc}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {/* Configuration Guide */}
            {block.configFields.length > 0 && (
              <Section title="CONFIGURATION GUIDE">
                {configGroups.map((group, gi) => (
                  <div key={gi} style={{ marginBottom: gi < configGroups.length - 1 ? 16 : 0 }}>
                    {configGroups.length > 1 && (
                      <div
                        style={{
                          fontFamily: F,
                          fontSize: FS.xxs,
                          color: T.dim,
                          fontWeight: 600,
                          letterSpacing: '0.06em',
                          marginBottom: 6,
                          textTransform: 'uppercase',
                        }}
                      >
                        {group.label}
                      </div>
                    )}
                    <div
                      style={{
                        background: T.surface0,
                        border: `1px solid ${T.border}`,
                        borderRadius: 6,
                        overflow: 'hidden',
                      }}
                    >
                      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr>
                            <Th>Parameter</Th>
                            <Th>Type</Th>
                            <Th>Default</Th>
                            <Th>Description</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {group.fields.map((f) => (
                            <tr key={f.name}>
                              <Td>
                                <span style={{ fontWeight: 700, color: T.text }}>{f.label}</span>
                              </Td>
                              <Td>
                                <span
                                  style={{
                                    padding: '1px 5px',
                                    background: `${T.cyan}12`,
                                    borderRadius: 3,
                                    fontFamily: F,
                                    fontSize: FS.xxs,
                                    color: T.cyan,
                                  }}
                                >
                                  {f.type}
                                </span>
                              </Td>
                              <Td>
                                <span
                                  style={{
                                    fontFamily: "'JetBrains Mono', monospace",
                                    fontSize: FS.xxs,
                                    color: T.dim,
                                  }}
                                >
                                  {block.defaultConfig[f.name] !== undefined
                                    ? String(block.defaultConfig[f.name]).substring(0, 40)
                                    : '-'}
                                </span>
                              </Td>
                              <Td>
                                <span style={{ color: T.dim, fontSize: FS.xxs }}>
                                  {f.description || '-'}
                                </span>
                              </Td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}

                {/* Advanced config expandable */}
                {advancedConfig && (
                  <div style={{ marginTop: 12 }}>
                    <button
                      onClick={() => setShowAdvanced(!showAdvanced)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        background: T.surface2,
                        border: `1px solid ${T.border}`,
                        borderRadius: 4,
                        padding: '6px 12px',
                        cursor: 'pointer',
                        color: T.sec,
                        fontFamily: F,
                        fontSize: FS.xs,
                        fontWeight: 700,
                        letterSpacing: '0.06em',
                        width: '100%',
                        transition: 'all 0.15s',
                      }}
                    >
                      {showAdvanced ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                      ADVANCED PARAMETERS ({Object.keys(advancedConfig.defaults).length})
                    </button>
                    {showAdvanced && (
                      <div
                        style={{
                          background: T.surface0,
                          border: `1px solid ${T.border}`,
                          borderTop: 'none',
                          borderRadius: '0 0 6px 6px',
                          overflow: 'hidden',
                        }}
                      >
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                          <thead>
                            <tr>
                              <Th>Param</Th>
                              <Th>Default</Th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(advancedConfig.defaults).map(([key, val]) => (
                              <tr key={key}>
                                <Td>
                                  <span style={{ fontWeight: 600 }}>{key}</span>
                                </Td>
                                <Td>
                                  <span
                                    style={{
                                      color: T.cyan,
                                      fontFamily: "'JetBrains Mono', monospace",
                                      fontSize: FS.xxs,
                                    }}
                                  >
                                    {Array.isArray(val) ? JSON.stringify(val) : String(val)}
                                  </span>
                                </Td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </Section>
            )}

            {/* Tips */}
            {block.detail?.tips && block.detail.tips.length > 0 && (
              <Section title="TIPS">
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {block.detail.tips.map((tip, i) => (
                    <div
                      key={i}
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: 10,
                        padding: '10px 14px',
                        fontFamily: F,
                        fontSize: FS.sm,
                        color: T.sec,
                        lineHeight: 1.6,
                        background: `${T.amber}08`,
                        border: `1px solid ${T.amber}20`,
                        borderRadius: 6,
                      }}
                    >
                      <Lightbulb
                        size={12}
                        color={T.amber}
                        style={{ marginTop: 2, flexShrink: 0 }}
                      />
                      {tip}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Code Preview */}
            {block.detail?.codePreview && (
              <Section title="CODE PREVIEW">
                <div
                  style={{
                    background: T.surface0,
                    border: `1px solid ${T.border}`,
                    borderRadius: 6,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '6px 12px',
                      borderBottom: `1px solid ${T.border}`,
                      background: T.surface2,
                    }}
                  >
                    <Code size={10} color={T.dim} />
                    <span
                      style={{
                        fontFamily: F,
                        fontSize: FS.xxs,
                        color: T.dim,
                        letterSpacing: '0.06em',
                      }}
                    >
                      PREVIEW
                    </span>
                  </div>
                  <pre
                    style={{
                      background: T.surface0,
                      padding: 14,
                      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                      fontSize: 10,
                      color: T.sec,
                      lineHeight: 1.7,
                      overflow: 'auto',
                      maxHeight: 300,
                      margin: 0,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {block.detail.codePreview}
                  </pre>
                </div>
              </Section>
            )}
          </div>

          {/* Sidebar (35%) */}
          <div style={{ flex: '0 0 35%', maxWidth: '35%', display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Data Flow visual */}
            <SidebarCard title="DATA FLOW" icon={<Zap size={10} color={T.cyan} />}>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 8,
                  padding: '8px 0',
                }}
              >
                {/* Inputs */}
                {block.inputs.length > 0 ? (
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 4,
                      width: '100%',
                    }}
                  >
                    {block.inputs.map((p) => (
                      <PortRow key={`i-${p.id}`} port={p} direction="input" />
                    ))}
                  </div>
                ) : (
                  <div
                    style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      color: T.dim,
                      fontStyle: 'italic',
                      padding: 4,
                    }}
                  >
                    No inputs (source block)
                  </div>
                )}

                {/* Arrow down */}
                <ArrowDown size={14} color={T.dim} />

                {/* Center block icon */}
                <div
                  style={{
                    width: 40,
                    height: 40,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: `${accent}18`,
                    border: `1px solid ${accent}40`,
                    borderRadius: 8,
                    boxShadow: `0 0 16px ${accent}15`,
                  }}
                >
                  <IconComponent size={18} color={accent} />
                </div>

                {/* Arrow down */}
                <ArrowDown size={14} color={T.dim} />

                {/* Outputs */}
                {block.outputs.length > 0 ? (
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 4,
                      width: '100%',
                    }}
                  >
                    {block.outputs.map((p) => (
                      <PortRow key={`o-${p.id}`} port={p} direction="output" />
                    ))}
                  </div>
                ) : (
                  <div
                    style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      color: T.dim,
                      fontStyle: 'italic',
                      padding: 4,
                    }}
                  >
                    No outputs (sink)
                  </div>
                )}
              </div>
            </SidebarCard>

            {/* Quick Stats */}
            <SidebarCard title="QUICK STATS" icon={<Layers size={10} color={T.cyan} />}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <StatRow label="Inputs" value={String(block.inputs.length)} />
                <StatRow label="Outputs" value={String(block.outputs.length)} />
                <StatRow label="Config Fields" value={String(block.configFields.length)} />
                <StatRow label="Maturity" value={block.maturity || 'stable'} />
                <StatRow label="Category" value={block.category} accent={accent} />
              </div>
            </SidebarCard>

            {/* Compatible Blocks */}
            {compatibleBlocks.length > 0 && (
              <SidebarCard
                title="COMPATIBLE BLOCKS"
                icon={<Settings size={10} color={T.cyan} />}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {compatibleBlocks.map(({ block: cb, direction }) => {
                    const CbIcon = getIcon(cb.icon)
                    const cbAccent = cb.accent || T.cyan
                    return (
                      <div
                        key={`${direction}-${cb.type}`}
                        onClick={() => onSelectBlock?.(cb)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          padding: '6px 8px',
                          background: T.surface0,
                          border: `1px solid ${T.border}`,
                          borderLeft: `3px solid ${cbAccent}`,
                          borderRadius: 4,
                          cursor: onSelectBlock ? 'pointer' : 'default',
                          transition: 'all 0.15s',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = T.surface2
                          e.currentTarget.style.borderColor = T.borderHi
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = T.surface0
                          e.currentTarget.style.borderColor = T.border
                        }}
                      >
                        <CbIcon size={12} color={cbAccent} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div
                            style={{
                              fontFamily: F,
                              fontSize: FS.xs,
                              color: T.text,
                              fontWeight: 600,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {cb.name}
                          </div>
                          <div
                            style={{
                              fontFamily: F,
                              fontSize: FS.xxs,
                              color: T.dim,
                            }}
                          >
                            {direction === 'input' ? 'Feeds into' : 'Receives from'} this block
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </SidebarCard>
            )}
          </div>
        </div>
      </div>

      {/* Footer CTA */}
      <div
        style={{
          padding: '14px 24px',
          borderTop: `1px solid ${T.border}`,
          background: T.surface1,
          flexShrink: 0,
          backdropFilter: 'blur(12px)',
        }}
      >
        <button
          onClick={handleAddToCanvas}
          style={{
            width: '100%',
            padding: '12px 20px',
            background: T.cyan,
            border: 'none',
            borderRadius: 6,
            color: '#000',
            fontFamily: FD,
            fontSize: FS.md,
            fontWeight: 700,
            cursor: 'pointer',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            transition: 'all 0.15s',
            boxShadow: `0 0 20px ${T.cyan}30`,
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.boxShadow = `0 0 32px ${T.cyan}50`
            e.currentTarget.style.transform = 'translateY(-1px)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.boxShadow = `0 0 20px ${T.cyan}30`
            e.currentTarget.style.transform = 'translateY(0)'
          }}
        >
          <PlusCircle size={14} />
          ADD TO CANVAS
        </button>
      </div>
    </motion.div>
  )
}

// ── Sub-components ──

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        background: `linear-gradient(180deg, ${T.surface1} 0%, ${T.surface0} 100%)`,
        border: `1px solid ${T.border}`,
        borderRadius: 8,
        overflow: 'hidden',
        backdropFilter: 'blur(8px)',
      }}
    >
      <div
        style={{
          padding: '8px 16px',
          borderBottom: `1px solid ${T.border}`,
          background: T.surface2,
        }}
      >
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            fontWeight: 700,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
          }}
        >
          {title}
        </span>
      </div>
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  )
}

function SidebarCard({
  title,
  icon,
  children,
}: {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div
      style={{
        background: `linear-gradient(180deg, ${T.surface1} 0%, ${T.surface0} 100%)`,
        border: `1px solid ${T.border}`,
        borderRadius: 8,
        overflow: 'hidden',
        backdropFilter: 'blur(8px)',
      }}
    >
      <div
        style={{
          padding: '8px 12px',
          borderBottom: `1px solid ${T.border}`,
          background: T.surface2,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        {icon}
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            fontWeight: 700,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
          }}
        >
          {title}
        </span>
      </div>
      <div style={{ padding: 12 }}>{children}</div>
    </div>
  )
}

function PortRow({ port }: { port: PortDefinition; direction: 'input' | 'output' }) {
  const color = getPortColor(port.dataType)
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '4px 8px',
        background: `${color}08`,
        border: `1px solid ${color}20`,
        borderRadius: 4,
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: port.required ? color : 'transparent',
          border: port.required ? 'none' : `1.5px solid ${color}`,
          flexShrink: 0,
          boxShadow: `0 0 6px ${color}40`,
        }}
      />
      <span
        style={{
          fontFamily: F,
          fontSize: FS.xs,
          color: T.text,
          fontWeight: 600,
          flex: 1,
        }}
      >
        {port.label}
      </span>
      <span
        style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: color,
          fontWeight: 600,
        }}
      >
        {port.dataType}
      </span>
      {!port.required && (
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            fontStyle: 'italic',
          }}
        >
          opt
        </span>
      )}
    </div>
  )
}

function StatRow({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>{label}</span>
      <span
        style={{
          fontFamily: F,
          fontSize: FS.xs,
          color: accent || T.text,
          fontWeight: 600,
          textTransform: 'capitalize',
        }}
      >
        {value}
      </span>
    </div>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      style={{
        fontFamily: F,
        fontSize: FS.xxs,
        color: T.dim,
        fontWeight: 700,
        letterSpacing: '0.08em',
        textAlign: 'left',
        padding: '6px 10px',
        borderBottom: `1px solid ${T.border}`,
        textTransform: 'uppercase',
        background: T.surface2,
      }}
    >
      {children}
    </th>
  )
}

function Td({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <td
      style={{
        fontFamily: F,
        fontSize: FS.xs,
        color: T.sec,
        padding: '6px 10px',
        borderBottom: `1px solid ${T.border}`,
        ...style,
      }}
    >
      {children}
    </td>
  )
}
