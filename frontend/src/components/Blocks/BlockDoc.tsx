import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS, CATEGORY_COLORS } from '@/lib/design-tokens'
import { getBlockDefinition, getPortColor } from '@/lib/block-registry'
import type { ConfigField, PortDefinition } from '@/lib/block-registry-types'

type PopoverSide = 'top' | 'bottom' | 'left' | 'right'

interface BlockDocProps {
  blockType: string | null
  anchor?: { x: number; y: number; width?: number; height?: number } | null
  visible: boolean
  onClose?: () => void
}

function computeSide(
  anchor: { x: number; y: number; width?: number; height?: number },
  popoverWidth: number,
  popoverHeight: number
): PopoverSide {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const aw = anchor.width ?? 0
  const ah = anchor.height ?? 0

  // Try right first (most natural for palette hover)
  if (anchor.x + aw + popoverWidth + 16 < vw) return 'right'
  // Then left
  if (anchor.x - popoverWidth - 16 > 0) return 'left'
  // Then below
  if (anchor.y + ah + popoverHeight + 16 < vh) return 'bottom'
  // Then above
  return 'top'
}

function getPosition(
  side: PopoverSide,
  anchor: { x: number; y: number; width?: number; height?: number }
): { left: number; top: number } {
  const aw = anchor.width ?? 0
  const ah = anchor.height ?? 0

  switch (side) {
    case 'right':
      return { left: anchor.x + aw + 8, top: anchor.y }
    case 'left':
      return { left: anchor.x - 360 - 8, top: anchor.y }
    case 'bottom':
      return { left: anchor.x, top: anchor.y + ah + 8 }
    case 'top':
      return { left: anchor.x, top: anchor.y - 400 - 8 }
  }
}

export default function BlockDoc({ blockType, anchor, visible, onClose }: BlockDocProps) {
  const block = blockType ? getBlockDefinition(blockType) : undefined
  const popoverRef = useRef<HTMLDivElement>(null)

  // Close on Escape
  useEffect(() => {
    if (!visible) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [visible, onClose])

  // Close on outside click
  useEffect(() => {
    if (!visible) return
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose?.()
      }
    }
    // Small delay to avoid closing on the click that opened it
    const timer = setTimeout(() => window.addEventListener('mousedown', handler), 100)
    return () => {
      clearTimeout(timer)
      window.removeEventListener('mousedown', handler)
    }
  }, [visible, onClose])

  if (!block || !visible) return null

  const effectiveAnchor = anchor ?? { x: window.innerWidth / 2 - 180, y: 120 }
  const popoverWidth = 360
  const popoverHeight = 420
  const side = computeSide(effectiveAnchor, popoverWidth, popoverHeight)
  const pos = getPosition(side, effectiveAnchor)

  const catColor = CATEGORY_COLORS[block.category] || T.dim

  return (
    <AnimatePresence>
      <motion.div
        ref={popoverRef}
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        transition={{ duration: 0.15 }}
        style={{
          position: 'fixed',
          left: pos.left,
          top: pos.top,
          width: popoverWidth,
          maxHeight: popoverHeight,
          overflowY: 'auto',
          zIndex: 10000,
          background: `linear-gradient(145deg, ${T.surface2} 0%, ${T.surface1} 100%)`,
          border: `1px solid ${T.borderHi}`,
          borderRadius: 10,
          boxShadow: `0 16px 48px ${T.shadowHeavy}`,
          padding: 16,
          scrollbarWidth: 'thin',
        }}
      >
        {/* Header: name + category badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <span
            style={{
              fontFamily: F,
              fontSize: FS.lg,
              fontWeight: 700,
              color: T.text,
            }}
          >
            {block.name}
          </span>
          <span
            style={{
              fontFamily: F,
              fontSize: 9,
              color: catColor,
              background: `${catColor}15`,
              border: `1px solid ${catColor}30`,
              padding: '2px 8px',
              borderRadius: 4,
              fontWeight: 700,
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
            }}
          >
            {block.category}
          </span>
        </div>

        {/* Description */}
        <p
          style={{
            fontFamily: F,
            fontSize: FS.sm,
            color: T.sec,
            lineHeight: 1.6,
            margin: '0 0 12px',
          }}
        >
          {block.description}
        </p>

        {/* Inputs table */}
        {block.inputs.length > 0 && (
          <PortSection title="Inputs" ports={block.inputs} />
        )}

        {/* Side inputs */}
        {block.side_inputs && block.side_inputs.length > 0 && (
          <PortSection title="Side Inputs" ports={block.side_inputs} />
        )}

        {/* Outputs table */}
        {block.outputs.length > 0 && (
          <PortSection title="Outputs" ports={block.outputs} />
        )}

        {/* Configuration table */}
        {block.configFields.length > 0 && (
          <ConfigSection fields={block.configFields} />
        )}

        {/* Example usage (if present in block detail) */}
        {block.detail?.useCases && block.detail.useCases.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <SectionHeader title="Example Usage" />
            <ul
              style={{
                margin: '4px 0 0',
                paddingLeft: 16,
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.sec,
                lineHeight: 1.6,
              }}
            >
              {block.detail.useCases.map((uc, i) => (
                <li key={i}>{uc}</li>
              ))}
            </ul>
          </div>
        )}

        {/* How it works */}
        {block.detail?.howItWorks && (
          <div style={{ marginTop: 12 }}>
            <SectionHeader title="How It Works" />
            <p
              style={{
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.sec,
                lineHeight: 1.6,
                margin: '4px 0 0',
              }}
            >
              {block.detail.howItWorks}
            </p>
          </div>
        )}

        {/* Type ID footer */}
        <div
          style={{
            borderTop: `1px solid ${T.border}`,
            paddingTop: 8,
            marginTop: 12,
          }}
        >
          <span style={{ fontFamily: F, fontSize: 9, color: T.dim }}>
            type: {block.type} &middot; v{block.version}
          </span>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}

function SectionHeader({ title }: { title: string }) {
  return (
    <div
      style={{
        fontFamily: F,
        fontSize: FS.xxs,
        color: T.dim,
        fontWeight: 900,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        marginBottom: 4,
      }}
    >
      {title}
    </div>
  )
}

function PortSection({ title, ports }: { title: string; ports: PortDefinition[] }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <SectionHeader title={title} />
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontFamily: F,
          fontSize: FS.xxs,
        }}
      >
        <thead>
          <tr>
            <th style={thStyle}>Port</th>
            <th style={thStyle}>Type</th>
            <th style={{ ...thStyle, width: 24, textAlign: 'center' }}>Req</th>
          </tr>
        </thead>
        <tbody>
          {ports.map((port) => {
            const portColor = getPortColor(port.dataType)
            return (
              <tr key={port.id}>
                <td style={tdStyle}>
                  <span style={{ color: T.sec }}>{port.label}</span>
                </td>
                <td style={tdStyle}>
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                    }}
                  >
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: '50%',
                        background: portColor,
                        flexShrink: 0,
                      }}
                    />
                    <span style={{ color: portColor, fontWeight: 600 }}>
                      {port.dataType}
                    </span>
                  </span>
                </td>
                <td style={{ ...tdStyle, textAlign: 'center' }}>
                  {port.required && (
                    <span style={{ color: T.red, fontWeight: 900, fontSize: 12 }}>*</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ConfigSection({ fields }: { fields: ConfigField[] }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <SectionHeader title="Configuration" />
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontFamily: F,
          fontSize: FS.xxs,
        }}
      >
        <thead>
          <tr>
            <th style={thStyle}>Field</th>
            <th style={thStyle}>Type</th>
            <th style={thStyle}>Default</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => (
            <tr key={field.name}>
              <td style={tdStyle}>
                <div>
                  <span style={{ color: T.sec, fontWeight: 600 }}>
                    {field.label || field.name}
                  </span>
                  {field.mandatory && (
                    <span style={{ color: T.red, fontWeight: 900, fontSize: 10, marginLeft: 2 }}>*</span>
                  )}
                </div>
                {field.description && (
                  <div style={{ color: T.dim, fontSize: 9, lineHeight: 1.4, marginTop: 1 }}>
                    {field.description}
                  </div>
                )}
              </td>
              <td style={tdStyle}>
                <span style={{ color: T.dim }}>{field.type}</span>
              </td>
              <td style={tdStyle}>
                <span style={{ color: T.dim, fontFamily: "'JetBrains Mono', monospace", fontSize: 9 }}>
                  {field.default !== undefined && field.default !== null
                    ? String(field.default)
                    : '-'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '3px 6px',
  borderBottom: `1px solid ${T.border}`,
  color: T.dim,
  fontWeight: 700,
  fontSize: 9,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
}

const tdStyle: React.CSSProperties = {
  padding: '4px 6px',
  borderBottom: `1px solid ${T.border}40`,
  verticalAlign: 'top',
}
