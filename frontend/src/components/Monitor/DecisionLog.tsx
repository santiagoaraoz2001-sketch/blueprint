import { useState, useEffect } from 'react'
import { T, F, FS, FCODE } from '@/lib/design-tokens'
import { api } from '@/api/client'
import { CheckCircle, Play, XCircle, SkipForward, Filter } from 'lucide-react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Decision {
  id: string
  run_id: string
  node_id: string
  node_label: string
  decision: 'execute' | 'cache_hit' | 'cache_invalidated' | 'skipped'
  reason: string | null
  cache_fingerprint: string | null
  plan_hash: string | null
  timestamp: string | null
}

const DECISION_BADGE: Record<
  string,
  { bg: string; fg: string; icon: React.ReactNode; label: string }
> = {
  execute: {
    bg: '#5B96FF22',
    fg: '#5B96FF',
    icon: <Play size={10} />,
    label: 'Execute',
  },
  cache_hit: {
    bg: '#3EF07A22',
    fg: '#3EF07A',
    icon: <CheckCircle size={10} />,
    label: 'Cache Hit',
  },
  cache_invalidated: {
    bg: '#FF5E7222',
    fg: '#FF5E72',
    icon: <XCircle size={10} />,
    label: 'Invalidated',
  },
  skipped: {
    bg: '#7A879922',
    fg: '#7A8799',
    icon: <SkipForward size={10} />,
    label: 'Skipped',
  },
}

// ---------------------------------------------------------------------------
// DecisionLog Component
// ---------------------------------------------------------------------------

export default function DecisionLog({ runId }: { runId: string }) {
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string | null>(null)

  useEffect(() => {
    if (!runId) return
    setLoading(true)
    api
      .get<Decision[]>(`/runs/${runId}/decisions`)
      .then((data) => {
        setDecisions(data || [])
        setLoading(false)
      })
      .catch(() => {
        setDecisions([])
        setLoading(false)
      })
  }, [runId])

  const filtered = filter ? decisions.filter((d) => d.decision === filter) : decisions

  // Count by decision type
  const counts: Record<string, number> = {}
  for (const d of decisions) {
    counts[d.decision] = (counts[d.decision] || 0) + 1
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '8px 12px',
          borderBottom: `1px solid ${T.border}`,
          flexShrink: 0,
        }}
      >
        <span style={{ fontFamily: F, fontSize: FS.xxs, fontWeight: 700, color: T.dim, letterSpacing: '0.1em' }}>
          DECISIONS
        </span>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          ({decisions.length})
        </span>
        <div style={{ flex: 1 }} />

        {/* Filter buttons */}
        {Object.entries(DECISION_BADGE).map(([key, badge]) => {
          const count = counts[key] || 0
          if (count === 0) return null
          const isActive = filter === key
          return (
            <button
              key={key}
              onClick={() => setFilter(isActive ? null : key)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 3,
                padding: '2px 6px',
                background: isActive ? badge.bg : 'none',
                border: `1px solid ${isActive ? badge.fg + '40' : 'transparent'}`,
                borderRadius: 3,
                color: isActive ? badge.fg : T.dim,
                fontFamily: F,
                fontSize: 9,
                cursor: 'pointer',
              }}
            >
              {badge.icon}
              {count}
            </button>
          )
        })}
      </div>

      {/* Timeline */}
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 12px' }}>
        {loading && (
          <div style={{ color: T.dim, fontSize: FS.xs, textAlign: 'center', padding: 24 }}>
            Loading decisions...
          </div>
        )}
        {!loading && decisions.length === 0 && (
          <div style={{ color: T.dim, fontSize: FS.xs, textAlign: 'center', padding: 24 }}>
            No execution decisions recorded for this run.
            <br />
            <span style={{ fontSize: FS.xxs }}>
              Decisions are recorded for runs started after this feature was enabled.
            </span>
          </div>
        )}
        {!loading &&
          filtered.map((d, idx) => {
            const badge = DECISION_BADGE[d.decision] || DECISION_BADGE.execute
            const timeStr = d.timestamp
              ? new Date(d.timestamp).toLocaleTimeString()
              : ''

            return (
              <div
                key={d.id}
                style={{
                  display: 'flex',
                  gap: 10,
                  padding: '6px 0',
                  borderBottom:
                    idx < filtered.length - 1 ? `1px solid ${T.border}08` : 'none',
                }}
              >
                {/* Timeline dot */}
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    flexShrink: 0,
                    width: 20,
                  }}
                >
                  <div
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: badge.fg,
                      boxShadow: `0 0 6px ${badge.fg}40`,
                      marginTop: 3,
                    }}
                  />
                  {idx < filtered.length - 1 && (
                    <div
                      style={{
                        width: 1,
                        flex: 1,
                        background: T.border,
                        marginTop: 2,
                      }}
                    />
                  )}
                </div>

                {/* Content */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                    <span style={{ fontSize: FS.xs, color: T.text, fontWeight: 500 }}>
                      {d.node_label}
                    </span>
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 3,
                        padding: '1px 6px',
                        borderRadius: 3,
                        background: badge.bg,
                        color: badge.fg,
                        fontSize: 9,
                        fontWeight: 600,
                      }}
                    >
                      {badge.icon}
                      {badge.label}
                    </span>
                    <span style={{ fontSize: 9, color: T.dim, marginLeft: 'auto' }}>
                      {timeStr}
                    </span>
                  </div>
                  {d.reason && (
                    <div style={{ fontSize: FS.xxs, color: T.dim, lineHeight: 1.4 }}>
                      {d.reason}
                    </div>
                  )}
                  {d.cache_fingerprint && (
                    <code
                      style={{
                        fontFamily: FCODE,
                        fontSize: 9,
                        color: T.dim,
                        background: T.surface0,
                        padding: '1px 4px',
                        borderRadius: 2,
                      }}
                    >
                      fp: {d.cache_fingerprint.slice(0, 12)}
                    </code>
                  )}
                </div>
              </div>
            )
          })}
      </div>
    </div>
  )
}
