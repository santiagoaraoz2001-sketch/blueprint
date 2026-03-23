import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS } from '@/lib/design-tokens'
import { getBlockDefinition, getPortColor } from '@/lib/block-registry'

interface BlockTooltipProps {
  blockType: string
  position?: { x: number; y: number }
  visible: boolean
}

export default function BlockTooltip({ blockType, position, visible }: BlockTooltipProps) {
  const block = getBlockDefinition(blockType)
  if (!block) return null

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 4 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 4 }}
          transition={{ duration: 0.15 }}
          style={{
            position: 'absolute',
            left: position?.x ?? 0,
            top: position?.y ?? 0,
            zIndex: 1000,
            width: 320,
            maxHeight: 400,
            overflowY: 'auto',
            background: T.surface2,
            border: `1px solid ${T.borderHi}`,
            boxShadow: `0 8px 32px ${T.shadow}`,
            padding: 12,
            pointerEvents: 'none',
          }}
        >
          {/* Block header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <div style={{ width: 10, height: 10, background: block.accent, flexShrink: 0 }} />
            <span style={{ fontFamily: F, fontSize: FS.md, fontWeight: 700, color: T.text }}>
              {block.name}
            </span>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginLeft: 'auto' }}>
              {block.category.toUpperCase()}
            </span>
          </div>

          {/* Description */}
          <p style={{ fontFamily: F, fontSize: FS.sm, color: T.sec, lineHeight: 1.5, margin: '0 0 8px' }}>
            {block.description}
          </p>

          {/* Inputs */}
          {block.inputs.length > 0 && (
            <div style={{ marginBottom: 6 }}>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 900, letterSpacing: '0.1em' }}>
                INPUTS
              </span>
              {block.inputs.map(p => (
                <div key={p.id} style={{ display: 'flex', gap: 4, padding: '2px 0' }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: getPortColor(p.dataType), flexShrink: 0, marginTop: 3 }} />
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>{p.label}</span>
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{p.dataType}</span>
                  {!p.required && <span style={{ fontFamily: F, fontSize: 4.5, color: T.dim }}>(opt)</span>}
                </div>
              ))}
            </div>
          )}

          {/* Outputs */}
          {block.outputs.length > 0 && (
            <div style={{ marginBottom: 6 }}>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 900, letterSpacing: '0.1em' }}>
                OUTPUTS
              </span>
              {block.outputs.map(p => (
                <div key={p.id} style={{ display: 'flex', gap: 4, padding: '2px 0' }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: getPortColor(p.dataType), flexShrink: 0, marginTop: 3 }} />
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>{p.label}</span>
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{p.dataType}</span>
                </div>
              ))}
            </div>
          )}

          {/* Config fields */}
          {block.configFields.length > 0 && (
            <div style={{ marginBottom: 4 }}>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 900, letterSpacing: '0.1em' }}>
                CONFIGURATION
              </span>
              {block.configFields.map(c => (
                <div key={c.name} style={{ padding: '2px 0' }}>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, fontWeight: 700 }}>{c.label || c.name}</span>
                    <span style={{ fontFamily: F, fontSize: 4.5, color: T.dim }}>({c.type})</span>
                  </div>
                  {c.description && (
                    <span style={{ fontFamily: F, fontSize: 4.5, color: T.dim, lineHeight: 1.4 }}>
                      {c.description}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Type ID */}
          <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 6, marginTop: 4 }}>
            <span style={{ fontFamily: F, fontSize: 4.5, color: T.dim }}>
              TYPE: {block.type}
            </span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
