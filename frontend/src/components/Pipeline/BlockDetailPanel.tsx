import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS } from '@/lib/design-tokens'
import { getBlockDefinition, getPortColor } from '@/lib/block-registry'
import { getAdvancedConfig } from '@/lib/advanced-configs'
import { getIcon } from '@/lib/icon-utils'
import { useUIStore } from '@/stores/uiStore'
import { X, ArrowRight, ChevronDown, ChevronRight, Code, GitFork, Lightbulb } from 'lucide-react'

interface BlockDetailPanelProps {
  blockType: string | null
  onClose: () => void
  onAddBlock?: (type: string) => void
}

export default function BlockDetailPanel({ blockType, onClose, onAddBlock }: BlockDetailPanelProps) {
  const [showAdvanced, setShowAdvanced] = useState(false)

  if (!blockType) return null
  const def = getBlockDefinition(blockType)
  if (!def) return null

  const Icon = getIcon(def.icon)
  const accent = def.accent || T.cyan
  const advancedConfig = getAdvancedConfig(blockType)

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 9998,
          background: T.shadowHeavy,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: -10 }}
        transition={{ duration: 0.2 }}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 520,
          maxHeight: '80vh',
          background: T.surface1,
          border: `1px solid ${T.borderHi}`,
          borderRadius: 12,
          boxShadow: `0 24px 80px ${T.shadowHeavy}`,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Accent bar */}
        <div style={{ height: 3, background: `linear-gradient(90deg, ${accent}, ${accent}40, transparent)` }} />

        {/* Header */}
        <div style={{
          padding: '14px 16px',
          borderBottom: `1px solid ${T.border}`,
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 32, height: 32, borderRadius: 6,
            background: `linear-gradient(135deg, ${T.surface3}, ${T.surface1})`,
            border: `1px solid ${T.borderHi}`,
            boxShadow: `0 0 12px ${accent}30`,
          }}>
            <Icon size={16} color={accent} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700 }}>{def.name}</div>
            <div style={{
              fontFamily: F, fontSize: FS.xxs, color: accent,
              letterSpacing: '0.1em', fontWeight: 700, textTransform: 'uppercase',
            }}>
              {def.category}
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 4 }}>
            <X size={14} />
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Description */}
          <div>
            <SectionLabel>DESCRIPTION</SectionLabel>
            <p style={{ fontFamily: F, fontSize: FS.sm, color: T.sec, lineHeight: 1.6, margin: 0 }}>
              {def.description}
            </p>
          </div>

          {/* Inputs */}
          {def.inputs.length > 0 && (
            <div>
              <SectionLabel>INPUTS</SectionLabel>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <Th>Port</Th>
                    <Th>Type</Th>
                    <Th>Required</Th>
                  </tr>
                </thead>
                <tbody>
                  {def.inputs.map(port => (
                    <tr key={port.id}>
                      <Td>{port.label}</Td>
                      <Td>
                        <span style={{ color: getPortColor(port.dataType), fontWeight: 700 }}>{port.dataType}</span>
                      </Td>
                      <Td>{port.required ? 'Yes' : 'No'}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Outputs */}
          {def.outputs.length > 0 && (
            <div>
              <SectionLabel>OUTPUTS</SectionLabel>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <Th>Port</Th>
                    <Th>Type</Th>
                  </tr>
                </thead>
                <tbody>
                  {def.outputs.map(port => (
                    <tr key={port.id}>
                      <Td>{port.label}</Td>
                      <Td>
                        <span style={{ color: getPortColor(port.dataType), fontWeight: 700 }}>{port.dataType}</span>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Configuration */}
          {def.configFields.length > 0 && (
            <div>
              <SectionLabel>CONFIGURATION</SectionLabel>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <Th>Field</Th>
                    <Th>Type</Th>
                    <Th>Default</Th>
                  </tr>
                </thead>
                <tbody>
                  {def.configFields.map(field => (
                    <tr key={field.name}>
                      <Td>{field.label}</Td>
                      <Td style={{ color: T.dim }}>{field.type}</Td>
                      <Td style={{ color: T.dim }}>
                        {def.defaultConfig[field.name] !== undefined
                          ? String(def.defaultConfig[field.name])
                          : '-'}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Advanced Configuration */}
          {advancedConfig && (
            <div>
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  background: 'none', border: `1px solid ${T.border}`,
                  borderRadius: 4, padding: '6px 10px', cursor: 'pointer',
                  color: T.sec, fontFamily: F, fontSize: FS.xs, fontWeight: 700,
                  letterSpacing: '0.06em', width: '100%',
                }}
              >
                <Code size={10} color={T.dim} />
                {showAdvanced ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                ADVANCED PARAMETERS
                <span style={{ marginLeft: 'auto', fontSize: FS.xxs, color: T.dim, fontWeight: 500 }}>
                  {Object.keys(advancedConfig.defaults).length} params
                </span>
              </button>
              {showAdvanced && (
                <div style={{ marginTop: 8 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr>
                        <Th>Parameter</Th>
                        <Th>Default</Th>
                        <Th>Type</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(advancedConfig.defaults).map(([key, val]) => {
                        const schema = advancedConfig.schema[key]
                        return (
                          <tr key={key}>
                            <Td>
                              <span style={{ color: T.text, fontWeight: 600 }}>{key}</span>
                              {schema?.description && (
                                <div style={{ fontSize: '7px', color: T.dim, marginTop: 1 }}>
                                  {schema.description}
                                </div>
                              )}
                            </Td>
                            <Td style={{ color: T.cyan, fontFamily: 'monospace', fontSize: FS.xxs }}>
                              {Array.isArray(val) ? JSON.stringify(val) : String(val)}
                            </Td>
                            <Td style={{ color: T.dim }}>{schema?.type || typeof val}</Td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Block Detail Info */}
          {def.detail && (
            <div>
              <SectionLabel>DETAILS</SectionLabel>
              {def.detail.format && (
                <div style={{
                  padding: '8px 12px', background: T.surface0, border: `1px solid ${T.border}`, borderRadius: 6,
                  fontFamily: F, fontSize: FS.xs, color: T.sec, marginBottom: 8,
                }}>
                  <span style={{ color: T.dim, fontSize: FS.xxs, fontWeight: 700, letterSpacing: '0.08em' }}>FORMAT: </span>
                  {def.detail.format}
                  {def.detail.formatEditable && (
                    <span style={{ marginLeft: 8, color: accent, fontSize: FS.xxs }}>• editable</span>
                  )}
                </div>
              )}
              {def.detail.howItWorks && (
                <div style={{
                  padding: '8px 12px', background: T.surface0, border: `1px solid ${T.border}`, borderRadius: 6,
                  fontFamily: F, fontSize: FS.xs, color: T.sec, lineHeight: 1.6, marginBottom: 8,
                }}>
                  <span style={{ color: T.dim, fontSize: FS.xxs, fontWeight: 700, letterSpacing: '0.08em' }}>HOW IT WORKS: </span>
                  {def.detail.howItWorks}
                </div>
              )}
              {def.detail.tips && def.detail.tips.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {def.detail.tips.map((tip, i) => (
                    <div key={i} style={{
                      display: 'flex', alignItems: 'flex-start', gap: 6,
                      padding: '4px 8px', fontFamily: F, fontSize: FS.xxs, color: T.sec, lineHeight: 1.5,
                    }}>
                      <Lightbulb size={9} color={T.amber} style={{ marginTop: 2, flexShrink: 0 }} />
                      {tip}
                    </div>
                  ))}
                </div>
              )}
              {def.detail.useCases && def.detail.useCases.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700, letterSpacing: '0.08em', padding: '0 8px' }}>USE CASES:</span>
                  {def.detail.useCases.map((uc, i) => (
                    <div key={i} style={{
                      display: 'flex', alignItems: 'flex-start', gap: 6,
                      padding: '4px 8px', fontFamily: F, fontSize: FS.xxs, color: T.sec, lineHeight: 1.5,
                    }}>
                      <ArrowRight size={9} color={accent} style={{ marginTop: 2, flexShrink: 0 }} />
                      {uc}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Data flow diagram */}
          <div>
            <SectionLabel>DATA FLOW</SectionLabel>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: 12,
              background: T.surface0,
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              flexWrap: 'wrap',
            }}>
              {def.inputs.map((p, i) => (
                <span key={`i-${i}`} style={{
                  padding: '2px 8px', borderRadius: 4,
                  background: `${getPortColor(p.dataType)}15`,
                  border: `1px solid ${getPortColor(p.dataType)}30`,
                  fontFamily: F, fontSize: FS.xxs, color: getPortColor(p.dataType), fontWeight: 700,
                }}>
                  {p.label}
                </span>
              ))}
              <ArrowRight size={12} color={T.dim} />
              <span style={{
                padding: '4px 10px', borderRadius: 4,
                background: `${accent}15`, border: `1px solid ${accent}30`,
                fontFamily: F, fontSize: FS.xs, color: accent, fontWeight: 700,
              }}>
                {def.name}
              </span>
              <ArrowRight size={12} color={T.dim} />
              {def.outputs.map((p, i) => (
                <span key={`o-${i}`} style={{
                  padding: '2px 8px', borderRadius: 4,
                  background: `${getPortColor(p.dataType)}15`,
                  border: `1px solid ${getPortColor(p.dataType)}30`,
                  fontFamily: F, fontSize: FS.xxs, color: getPortColor(p.dataType), fontWeight: 700,
                }}>
                  {p.label}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div style={{
          padding: '12px 16px',
          borderTop: `1px solid ${T.border}`,
          display: 'flex', flexDirection: 'column', gap: 8,
        }}>
          {onAddBlock && (
            <button
              onClick={() => onAddBlock(def.type)}
              style={{
                width: '100%',
                padding: '10px 16px',
                background: T.cyan,
                border: 'none',
                borderRadius: 4,
                color: '#000',
                fontFamily: F,
                fontSize: FS.sm,
                fontWeight: 700,
                cursor: 'pointer',
                letterSpacing: '0.06em',
              }}
            >
              ADD TO CANVAS
            </button>
          )}
          <button
            onClick={() => {
              // Navigate to Workshop with this block pre-loaded for forking
              useUIStore.getState().setView('workshop')
              // Store the block type to fork in sessionStorage for Workshop to pick up
              sessionStorage.setItem('blueprint-fork-block', def.type)
              onClose()
            }}
            style={{
              width: '100%',
              padding: '8px 16px',
              background: `${accent}15`,
              border: `1px solid ${accent}30`,
              borderRadius: 4,
              color: accent,
              fontFamily: F,
              fontSize: FS.xs,
              fontWeight: 700,
              cursor: 'pointer',
              letterSpacing: '0.06em',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            }}
          >
            <GitFork size={11} />
            FORK AS CUSTOM BLOCK
          </button>
        </div>
      </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontFamily: F, fontSize: FS.xxs, color: T.dim,
      fontWeight: 700, letterSpacing: '0.12em', marginBottom: 8,
      textTransform: 'uppercase',
    }}>
      {children}
    </div>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th style={{
      fontFamily: F, fontSize: FS.xxs, color: T.dim,
      fontWeight: 700, letterSpacing: '0.08em',
      textAlign: 'left', padding: '4px 8px',
      borderBottom: `1px solid ${T.border}`,
      textTransform: 'uppercase',
    }}>
      {children}
    </th>
  )
}

function Td({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <td style={{
      fontFamily: F, fontSize: FS.xs, color: T.sec,
      padding: '6px 8px',
      borderBottom: `1px solid ${T.border}`,
      ...style,
    }}>
      {children}
    </td>
  )
}
