import { T, F, FS } from '@/lib/design-tokens'
import { Database, ArrowRight, GitBranch, Package } from 'lucide-react'

/** A single step in the lineage chain */
export interface LineageStep {
  id: string
  label: string
  type: 'source' | 'transform' | 'output'
  detail?: string
}

interface DataLineageViewProps {
  /** Source datasets that feed into the pipeline */
  sources: { name: string; origin: string }[]
  /** Transformations applied in order */
  transformations: { name: string; description: string }[]
  /** Output artifacts produced */
  outputs: { name: string; format: string }[]
}

const boxStyle = (accent: string): React.CSSProperties => ({
  padding: '10px 14px',
  background: T.surface2,
  border: `1px solid ${T.border}`,
  borderLeft: `3px solid ${accent}`,
  display: 'flex',
  flexDirection: 'column',
  gap: 3,
  minWidth: 160,
})

const titleStyle: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.sm,
  fontWeight: 700,
  color: T.text,
  letterSpacing: '0.04em',
}

const detailStyle: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.xxs,
  color: T.dim,
  lineHeight: 1.4,
}

const arrowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: T.dim,
  flexShrink: 0,
}

const sectionLabelStyle: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.xxs,
  fontWeight: 700,
  color: T.dim,
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  marginBottom: 8,
}

export default function DataLineageView({
  sources,
  transformations,
  outputs,
}: DataLineageViewProps) {
  const hasContent = sources.length > 0 || transformations.length > 0 || outputs.length > 0

  if (!hasContent) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
          No lineage data available. Run a pipeline to see data flow.
        </span>
      </div>
    )
  }

  return (
    <div style={{ padding: 16, overflow: 'auto', height: '100%' }}>
      {/* Title */}
      <div
        style={{
          fontFamily: F,
          fontSize: FS.lg,
          fontWeight: 700,
          color: T.text,
          letterSpacing: '0.06em',
          marginBottom: 16,
        }}
      >
        DATA LINEAGE
      </div>

      {/* Flow diagram */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 0,
          overflowX: 'auto',
          paddingBottom: 12,
        }}
      >
        {/* Sources column */}
        {sources.length > 0 && (
          <div style={{ flexShrink: 0 }}>
            <div style={sectionLabelStyle}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Database size={8} />
                SOURCES
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {sources.map((src, i) => (
                <div key={i} style={boxStyle(T.cyan)}>
                  <span style={titleStyle}>{src.name}</span>
                  <span style={detailStyle}>{src.origin}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Arrow to transforms */}
        {sources.length > 0 && transformations.length > 0 && (
          <div style={{ ...arrowStyle, padding: '30px 12px 0' }}>
            <ArrowRight size={14} />
          </div>
        )}

        {/* Transformations column */}
        {transformations.length > 0 && (
          <div style={{ flexShrink: 0 }}>
            <div style={sectionLabelStyle}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <GitBranch size={8} />
                TRANSFORMATIONS
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {transformations.map((tr, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
                  <div style={boxStyle(T.amber)}>
                    <span style={titleStyle}>{tr.name}</span>
                    <span style={detailStyle}>{tr.description}</span>
                  </div>
                  {/* Internal arrow between transforms */}
                  {i < transformations.length - 1 && (
                    <div
                      style={{
                        position: 'relative',
                        width: 0,
                        height: 20,
                      }}
                    >
                      <div
                        style={{
                          position: 'absolute',
                          left: '50%',
                          top: 0,
                          transform: 'translateX(-50%)',
                          width: 1,
                          height: '100%',
                          background: T.border,
                        }}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Arrow to outputs */}
        {(sources.length > 0 || transformations.length > 0) && outputs.length > 0 && (
          <div style={{ ...arrowStyle, padding: '30px 12px 0' }}>
            <ArrowRight size={14} />
          </div>
        )}

        {/* Outputs column */}
        {outputs.length > 0 && (
          <div style={{ flexShrink: 0 }}>
            <div style={sectionLabelStyle}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Package size={8} />
                OUTPUTS
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {outputs.map((out, i) => (
                <div key={i} style={boxStyle(T.green)}>
                  <span style={titleStyle}>{out.name}</span>
                  <span style={detailStyle}>{out.format}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Summary table */}
      <div
        style={{
          marginTop: 24,
          borderTop: `1px solid ${T.border}`,
          paddingTop: 16,
        }}
      >
        <div style={sectionLabelStyle}>SUMMARY</div>
        <div style={{ display: 'flex', gap: 24 }}>
          <div>
            <span style={{ fontFamily: F, fontSize: FS.xl, fontWeight: 700, color: T.cyan }}>
              {sources.length}
            </span>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginLeft: 4 }}>
              {sources.length === 1 ? 'SOURCE' : 'SOURCES'}
            </span>
          </div>
          <div>
            <span style={{ fontFamily: F, fontSize: FS.xl, fontWeight: 700, color: T.amber }}>
              {transformations.length}
            </span>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginLeft: 4 }}>
              {transformations.length === 1 ? 'TRANSFORM' : 'TRANSFORMS'}
            </span>
          </div>
          <div>
            <span style={{ fontFamily: F, fontSize: FS.xl, fontWeight: 700, color: T.green }}>
              {outputs.length}
            </span>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginLeft: 4 }}>
              {outputs.length === 1 ? 'OUTPUT' : 'OUTPUTS'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
