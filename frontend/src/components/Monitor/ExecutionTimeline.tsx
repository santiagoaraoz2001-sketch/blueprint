/**
 * ExecutionTimeline — horizontal Gantt chart showing block execution.
 *
 * Each bar represents a block's execution. Width proportional to duration.
 * Colors: completed=teal, running=blue (animated pulse), pending=dark gray,
 * failed=red, cached/skipped=striped teal.
 * X-axis: wall-clock time relative to run start.
 * Y-axis: block names in execution order.
 * Click a bar: shows detail popover.
 */
import { useState, useMemo, useRef, useCallback } from 'react'
import { T, F, FS, FCODE } from '@/lib/design-tokens'
import { useMonitorStore, type TimelineBlock } from '@/stores/monitorStore'

const ROW_HEIGHT = 28
const LABEL_WIDTH = 140
const MIN_BAR_WIDTH = 4
const HEADER_HEIGHT = 24

interface PopoverData {
  block: TimelineBlock
  x: number
  y: number
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60000)
  const s = ((ms % 60000) / 1000).toFixed(0)
  return `${m}m ${s}s`
}

function formatTimestamp(ms: number): string {
  const d = new Date(ms)
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, '0'))
    .join(':')
}

function barColor(status: TimelineBlock['status']): string {
  switch (status) {
    case 'complete': return '#00BFA5'
    case 'running':  return '#5B96FF'
    case 'failed':   return '#EF5350'
    case 'cached':   return '#00BFA5'
    default:         return T.surface4
  }
}

export default function ExecutionTimeline() {
  const blocks = useMonitorStore((s) => s.blocks)
  const executionOrder = useMonitorStore((s) => s.executionOrder)
  const runStartTime = useMonitorStore((s) => s.runStartTime)
  const runStatus = useMonitorStore((s) => s.runStatus)

  const [popover, setPopover] = useState<PopoverData | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const orderedBlocks = useMemo(() => {
    return executionOrder.map((id) => blocks[id]).filter(Boolean)
  }, [executionOrder, blocks])

  // Compute time range
  const now = Date.now()
  const timeRange = useMemo(() => {
    if (!runStartTime || orderedBlocks.length === 0) {
      return { start: 0, end: 1000 }
    }
    const start = runStartTime
    let end = start + 1000 // minimum 1s range
    for (const block of orderedBlocks) {
      const blockEnd = block.endTime ?? now
      if (blockEnd > end) end = blockEnd
    }
    // Add 5% padding
    const range = end - start
    return { start, end: end + range * 0.05 }
  }, [runStartTime, orderedBlocks, now, runStatus])

  const totalDuration = timeRange.end - timeRange.start

  const handleBarClick = useCallback((block: TimelineBlock, e: React.MouseEvent) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return
    setPopover({
      block,
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    })
  }, [])

  if (orderedBlocks.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          fontFamily: F,
          fontSize: FS.xs,
          color: T.dim,
        }}
      >
        {runStatus === 'idle' ? 'Run a pipeline to see the execution timeline' : 'Waiting for blocks to start...'}
      </div>
    )
  }

  const chartWidth = 600 // will scale with container
  const chartHeight = orderedBlocks.length * ROW_HEIGHT

  // Generate X-axis ticks (adaptive based on duration)
  const tickCount = Math.min(6, Math.max(2, Math.floor(totalDuration / 1000)))
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => {
    const ms = (totalDuration / tickCount) * i
    return { ms, label: formatDuration(Math.round(ms)) }
  })

  return (
    <div
      ref={containerRef}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'auto',
        position: 'relative',
      }}
      onClick={() => setPopover(null)}
    >
      {/* Inline animation styles */}
      <style>{`
        @keyframes timeline-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        .timeline-bar-cached {
          background: repeating-linear-gradient(
            -45deg,
            #00BFA5,
            #00BFA5 3px,
            #00BFA580 3px,
            #00BFA580 6px
          ) !important;
        }
      `}</style>

      <div style={{ display: 'flex', minWidth: 'fit-content' }}>
        {/* Y-axis labels */}
        <div style={{ width: LABEL_WIDTH, flexShrink: 0, paddingTop: HEADER_HEIGHT }}>
          {orderedBlocks.map((block) => (
            <div
              key={block.nodeId}
              style={{
                height: ROW_HEIGHT,
                display: 'flex',
                alignItems: 'center',
                padding: '0 8px',
                fontFamily: F,
                fontSize: FS.xxs,
                color: block.status === 'pending' ? T.dim : T.sec,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={block.label}
            >
              {block.label}
            </div>
          ))}
        </div>

        {/* Chart area */}
        <div style={{ flex: 1, minWidth: 300, position: 'relative' }}>
          {/* X-axis header */}
          <div
            style={{
              height: HEADER_HEIGHT,
              display: 'flex',
              alignItems: 'flex-end',
              paddingBottom: 2,
              borderBottom: `1px solid ${T.border}`,
            }}
          >
            {ticks.map((tick, i) => (
              <div
                key={i}
                style={{
                  position: 'absolute',
                  left: `${(tick.ms / totalDuration) * 100}%`,
                  fontFamily: FCODE,
                  fontSize: 9,
                  color: T.dim,
                  transform: 'translateX(-50%)',
                }}
              >
                {tick.label}
              </div>
            ))}
          </div>

          {/* Bars */}
          <svg
            width="100%"
            height={chartHeight}
            viewBox={`0 0 ${chartWidth} ${chartHeight}`}
            preserveAspectRatio="none"
            style={{ display: 'block' }}
          >
            {/* Grid lines */}
            {ticks.map((tick, i) => (
              <line
                key={i}
                x1={(tick.ms / totalDuration) * chartWidth}
                y1={0}
                x2={(tick.ms / totalDuration) * chartWidth}
                y2={chartHeight}
                stroke={T.border}
                strokeWidth={0.5}
                strokeDasharray="2,4"
              />
            ))}

            {/* Row separators */}
            {orderedBlocks.map((_, i) => (
              <line
                key={`row-${i}`}
                x1={0}
                y1={(i + 1) * ROW_HEIGHT}
                x2={chartWidth}
                y2={(i + 1) * ROW_HEIGHT}
                stroke={T.border}
                strokeWidth={0.3}
                opacity={0.5}
              />
            ))}

            {/* Execution bars */}
            {orderedBlocks.map((block, i) => {
              const blockStart = block.startTime - timeRange.start
              const blockEnd = (block.endTime ?? now) - timeRange.start
              const x = (blockStart / totalDuration) * chartWidth
              const w = Math.max(((blockEnd - blockStart) / totalDuration) * chartWidth, MIN_BAR_WIDTH)
              const y = i * ROW_HEIGHT + 6
              const h = ROW_HEIGHT - 12
              const color = barColor(block.status)

              return (
                <g key={block.nodeId}>
                  {/* Bar */}
                  <rect
                    x={x}
                    y={y}
                    width={w}
                    height={h}
                    rx={3}
                    fill={color}
                    opacity={block.status === 'pending' ? 0.3 : 0.85}
                    style={{
                      cursor: 'pointer',
                      ...(block.status === 'running'
                        ? { animation: 'timeline-pulse 1.5s ease-in-out infinite' }
                        : {}),
                    }}
                    onClick={(e) => {
                      e.stopPropagation()
                      handleBarClick(block, e as unknown as React.MouseEvent)
                    }}
                  />
                  {/* Striped overlay for cached */}
                  {block.status === 'cached' && (
                    <rect
                      x={x}
                      y={y}
                      width={Math.max(w, 16)}
                      height={h}
                      rx={3}
                      fill="url(#stripes)"
                      opacity={0.5}
                    />
                  )}
                  {/* Duration label on bar (if wide enough) */}
                  {w > 40 && block.durationMs != null && (
                    <text
                      x={x + w / 2}
                      y={y + h / 2}
                      textAnchor="middle"
                      dominantBaseline="central"
                      fill="#fff"
                      fontFamily={FCODE}
                      fontSize={9}
                      fontWeight={600}
                    >
                      {formatDuration(block.durationMs)}
                    </text>
                  )}
                </g>
              )
            })}

            {/* Stripe pattern for cached blocks */}
            <defs>
              <pattern id="stripes" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
                <rect width="3" height="6" fill="rgba(255,255,255,0.15)" />
              </pattern>
            </defs>
          </svg>
        </div>
      </div>

      {/* Detail popover */}
      {popover && (
        <div
          style={{
            position: 'absolute',
            left: Math.min(popover.x, (containerRef.current?.clientWidth ?? 400) - 220),
            top: popover.y + 8,
            background: T.surface,
            border: `1px solid ${T.borderHi}`,
            borderRadius: 6,
            padding: '10px 14px',
            boxShadow: `0 8px 24px rgba(0,0,0,0.5)`,
            zIndex: 50,
            minWidth: 200,
            backdropFilter: 'blur(12px)',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 600, marginBottom: 6 }}>
            {popover.block.label}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <PopoverRow label="Status" value={popover.block.status} />
            <PopoverRow label="Type" value={popover.block.blockType} />
            <PopoverRow label="Start" value={formatTimestamp(popover.block.startTime)} />
            {popover.block.durationMs != null && (
              <PopoverRow label="Duration" value={formatDuration(popover.block.durationMs)} />
            )}
            {popover.block.primaryOutputType && (
              <PopoverRow label="Output" value={popover.block.primaryOutputType} />
            )}
            {popover.block.artifactCount != null && popover.block.artifactCount > 0 && (
              <PopoverRow label="Artifacts" value={String(popover.block.artifactCount)} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function PopoverRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', gap: 8 }}>
      <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, width: 56, flexShrink: 0 }}>
        {label}
      </span>
      <span style={{ fontFamily: FCODE, fontSize: FS.xxs, color: T.sec }}>
        {value}
      </span>
    </div>
  )
}
