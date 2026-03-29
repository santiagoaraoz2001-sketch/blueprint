import { useState, useEffect, useCallback, useRef } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { api } from '@/api/client'
import { Clock, Pencil, Star, Loader2 } from 'lucide-react'

interface TimelineEntry {
  run_id: string
  run_status: string
  best_in_project: boolean
  timestamp: string | null
  experiment_name: string | null
  auto_summary: string | null
  user_notes: string | null
  note_id: string | null
  duration_seconds: number | null
  metrics: Record<string, any>
}

interface TimelineResponse {
  project_id: string
  entries: TimelineEntry[]
  next_cursor: string | null
  has_more: boolean
}

interface ExperimentTimelineProps {
  projectId: string
  experiments?: { id: string; name: string }[]
}

const BADGE_COLORS = [
  '#4af6c3', '#3B82F6', '#f59e0b', '#8B5CF6', '#EC4899', '#22c55e', '#fb8b1e',
]

const PAGE_SIZE = 50

export default function ExperimentTimeline({ projectId, experiments }: ExperimentTimelineProps) {
  const [entries, setEntries] = useState<TimelineEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [filterExperiment, setFilterExperiment] = useState<string | null>(null)
  const [filterStarred, setFilterStarred] = useState(false)
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')
  const sentinelRef = useRef<HTMLDivElement>(null)

  // Color assignment for experiment names
  const experimentColors = new Map<string, string>()
  let colorIdx = 0

  const getExperimentColor = (name: string | null) => {
    if (!name) return T.dim
    if (!experimentColors.has(name)) {
      experimentColors.set(name, BADGE_COLORS[colorIdx % BADGE_COLORS.length])
      colorIdx++
    }
    return experimentColors.get(name)!
  }

  const buildQueryString = useCallback(
    (cursor?: string | null) => {
      const params = new URLSearchParams()
      if (filterExperiment) params.set('experiment_id', filterExperiment)
      if (filterStarred) params.set('starred_only', 'true')
      params.set('limit', String(PAGE_SIZE))
      if (cursor) params.set('cursor', cursor)
      return params.toString()
    },
    [filterExperiment, filterStarred],
  )

  // Initial fetch (resets on filter change)
  const fetchTimeline = useCallback(() => {
    const qs = buildQueryString()
    api
      .get<TimelineResponse>(`/projects/${projectId}/timeline?${qs}`)
      .then((data) => {
        setEntries(data.entries || [])
        setNextCursor(data.next_cursor)
        setHasMore(data.has_more)
      })
      .catch(() => {
        setEntries([])
        setNextCursor(null)
        setHasMore(false)
      })
      .finally(() => setLoading(false))
  }, [projectId, buildQueryString])

  // Load next page
  const fetchMore = useCallback(() => {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    const qs = buildQueryString(nextCursor)
    api
      .get<TimelineResponse>(`/projects/${projectId}/timeline?${qs}`)
      .then((data) => {
        setEntries((prev) => [...prev, ...(data.entries || [])])
        setNextCursor(data.next_cursor)
        setHasMore(data.has_more)
      })
      .catch(() => {
        setHasMore(false)
      })
      .finally(() => setLoadingMore(false))
  }, [projectId, nextCursor, loadingMore, buildQueryString])

  useEffect(() => {
    setLoading(true)
    setEntries([])
    setNextCursor(null)
    setHasMore(false)
    fetchTimeline()
  }, [fetchTimeline])

  // Intersection observer for infinite scroll
  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && hasMore && !loadingMore) {
          fetchMore()
        }
      },
      { rootMargin: '200px' },
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasMore, loadingMore, fetchMore])

  const handleSaveNote = useCallback(
    async (runId: string) => {
      try {
        await api.put(`/runs/${runId}/journal`, { user_notes: editText || null })
        setEditingNoteId(null)
        fetchTimeline()
      } catch {
        // Silently fail
      }
    },
    [editText, fetchTimeline],
  )

  return (
    <div style={{ padding: '0 0 20px' }}>
      {/* Header with filters */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
        flexWrap: 'wrap',
      }}>
        <Clock size={14} color={T.cyan} />
        <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 700 }}>
          Experiment Timeline
        </span>
        <div style={{ flex: 1 }} />

        {/* Starred filter */}
        <button
          onClick={() => setFilterStarred(!filterStarred)}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '3px 8px',
            background: filterStarred ? `${T.amber}18` : 'transparent',
            border: `1px solid ${filterStarred ? T.amber + '44' : T.border}`,
            borderRadius: 3, cursor: 'pointer',
            fontFamily: F, fontSize: FS.xxs,
            color: filterStarred ? T.amber : T.dim,
          }}
        >
          <Star size={10} />
          Starred
        </button>

        {/* Experiment filter */}
        {experiments && experiments.length > 0 && (
          <select
            value={filterExperiment || ''}
            onChange={(e) => setFilterExperiment(e.target.value || null)}
            style={{
              padding: '3px 8px',
              background: T.surface2,
              border: `1px solid ${T.border}`,
              borderRadius: 3,
              fontFamily: F, fontSize: FS.xxs, color: T.text,
            }}
          >
            <option value="">All experiments</option>
            {experiments.map((exp) => (
              <option key={exp.id} value={exp.id}>{exp.name}</option>
            ))}
          </select>
        )}
      </div>

      {/* Timeline entries */}
      {loading && (
        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, textAlign: 'center', padding: 20 }}>
          Loading timeline...
        </div>
      )}

      {!loading && entries.length === 0 && (
        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, textAlign: 'center', padding: 20 }}>
          No journal entries yet. Run experiments to populate the timeline.
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {entries.map((entry) => {
          const isEditing = editingNoteId === entry.run_id
          const badgeColor = getExperimentColor(entry.experiment_name)

          return (
            <div
              key={entry.run_id}
              style={{
                display: 'flex',
                gap: 10,
                padding: '8px 12px',
                background: entry.best_in_project ? `${T.amber}06` : 'transparent',
                borderLeft: entry.best_in_project ? `2px solid ${T.amber}` : '2px solid transparent',
                borderRadius: 2,
              }}
            >
              {/* Timestamp */}
              <div style={{
                fontFamily: F, fontSize: FS.xxs, color: T.dim,
                minWidth: 65, flexShrink: 0, paddingTop: 2,
              }}>
                {entry.timestamp
                  ? new Date(entry.timestamp).toLocaleDateString(undefined, {
                      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                    })
                  : '?'}
              </div>

              {/* Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                {/* Experiment badge */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                  {entry.experiment_name && (
                    <span style={{
                      fontFamily: F, fontSize: 9, color: badgeColor,
                      background: `${badgeColor}15`, padding: '1px 6px',
                      borderRadius: 3, letterSpacing: '0.03em',
                    }}>
                      {entry.experiment_name}
                    </span>
                  )}
                  {entry.best_in_project && (
                    <Star size={10} color={T.amber} fill={T.amber} />
                  )}
                  <span style={{
                    fontFamily: F, fontSize: 9,
                    color: entry.run_status === 'failed' ? T.red : T.dim,
                  }}>
                    {entry.run_status}
                  </span>
                  {entry.duration_seconds != null && (
                    <span style={{ fontFamily: F, fontSize: 9, color: T.dim }}>
                      {entry.duration_seconds >= 60
                        ? `${(entry.duration_seconds / 60).toFixed(1)}m`
                        : `${entry.duration_seconds.toFixed(0)}s`}
                    </span>
                  )}
                </div>

                {/* Auto summary */}
                {entry.auto_summary && (
                  <div style={{
                    fontFamily: F, fontSize: FS.xxs, color: T.dim,
                    fontStyle: 'italic', lineHeight: 1.5, marginBottom: 3,
                  }}>
                    {entry.auto_summary}
                  </div>
                )}

                {/* User notes (editable) */}
                {isEditing ? (
                  <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                    <textarea
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      autoFocus
                      onBlur={() => handleSaveNote(entry.run_id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          handleSaveNote(entry.run_id)
                        }
                      }}
                      style={{
                        flex: 1,
                        fontFamily: F, fontSize: FS.xxs, color: T.text,
                        background: T.surface2, border: `1px solid ${T.cyan}44`,
                        borderRadius: 3, padding: '4px 8px',
                        resize: 'vertical', minHeight: 40,
                        outline: 'none',
                      }}
                    />
                  </div>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 4 }}>
                    {entry.user_notes ? (
                      <div style={{
                        fontFamily: F, fontSize: FS.xxs, color: T.sec,
                        lineHeight: 1.5, flex: 1,
                        whiteSpace: 'pre-wrap',
                      }}>
                        {entry.user_notes}
                      </div>
                    ) : null}
                    <button
                      onClick={() => {
                        setEditingNoteId(entry.run_id)
                        setEditText(entry.user_notes || '')
                      }}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer',
                        padding: 2, flexShrink: 0, opacity: 0.4,
                      }}
                      title="Edit notes"
                    >
                      <Pencil size={10} color={T.dim} />
                    </button>
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {/* Infinite scroll sentinel + load-more indicator */}
        <div ref={sentinelRef} style={{ height: 1 }} />
        {loadingMore && (
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            gap: 6, padding: 12,
          }}>
            <Loader2 size={12} color={T.dim} style={{ animation: 'spin 1s linear infinite' }} />
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
              Loading more entries...
            </span>
          </div>
        )}
        {!hasMore && entries.length > 0 && (
          <div style={{
            fontFamily: F, fontSize: FS.xxs, color: T.dim,
            textAlign: 'center', padding: '8px 0',
          }}>
            {entries.length} {entries.length === 1 ? 'entry' : 'entries'} total
          </div>
        )}
      </div>
    </div>
  )
}
