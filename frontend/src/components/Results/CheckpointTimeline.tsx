import { useState, useEffect, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { api } from '@/api/client'
import { usePipelineStore } from '@/stores/pipelineStore'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceDot,
} from 'recharts'
import { Download, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'

interface Checkpoint {
  epoch: number
  path: string
  metrics: Record<string, number>
  timestamp: number
}

interface MetricsEvent {
  name: string
  value: number
  step?: number
}

interface CheckpointTimelineProps {
  runId: string
}

export default function CheckpointTimeline({ runId }: CheckpointTimelineProps) {
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([])
  const [metricsLog, setMetricsLog] = useState<MetricsEvent[]>([])
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<Checkpoint | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingModel, setLoadingModel] = useState(false)
  const addNode = usePipelineStore((s) => s.addNode)

  useEffect(() => {
    async function fetchData() {
      setLoading(true)
      try {
        const [ckptRes, metricsRes] = await Promise.all([
          api.get<{ checkpoints: Checkpoint[] }>(`/runs/${runId}/checkpoints`),
          api.get<MetricsEvent[]>(`/runs/${runId}/metrics-log`),
        ])
        setCheckpoints(ckptRes.checkpoints || [])
        setMetricsLog(metricsRes || [])
      } catch {
        // Silently handle — component will show empty state
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [runId])

  // Build loss curve data from metrics log
  const lossData = useMemo(() => {
    const points: { step: number; loss: number }[] = []
    for (const event of metricsLog) {
      if (
        (event.name === 'train/loss' || event.name === 'loss') &&
        event.step != null
      ) {
        points.push({ step: event.step, loss: event.value })
      }
    }
    return points.sort((a, b) => a.step - b.step)
  }, [metricsLog])

  // Map checkpoint epochs to their approximate step positions
  const checkpointMarkers = useMemo(() => {
    if (lossData.length === 0 || checkpoints.length === 0) return []
    // Find the closest loss data point for each checkpoint's epoch
    return checkpoints.map((ckpt) => {
      // Find matching checkpoint_epoch metric to get the step
      const epochMetric = metricsLog.find(
        (e) => e.name === `checkpoint_epoch_${ckpt.epoch}`
      )
      const step = epochMetric?.step ?? ckpt.epoch
      // Find the closest loss value at that step
      const closest = lossData.reduce((prev, curr) =>
        Math.abs(curr.step - step) < Math.abs(prev.step - step) ? curr : prev
      )
      return {
        ...ckpt,
        step: closest.step,
        loss: ckpt.metrics.loss ?? closest.loss,
      }
    })
  }, [checkpoints, lossData, metricsLog])

  const handleLoadAsModel = async (checkpoint: Checkpoint) => {
    setLoadingModel(true)
    try {
      const result = await api.post<{
        model_path: string
        source_run: string
        source_epoch: number
      }>(`/runs/${runId}/checkpoints/${checkpoint.epoch}/load`)

      // Add a model_selector node to the pipeline canvas
      const nodes = usePipelineStore.getState().nodes
      const maxX = nodes.length > 0
        ? Math.max(...nodes.map((n) => n.position.x)) + 300
        : 100
      const maxY = nodes.length > 0
        ? Math.max(...nodes.map((n) => n.position.y))
        : 100

      addNode('model_selector', { x: maxX, y: maxY })

      // Update the newly added node's config with the checkpoint path
      const updatedNodes = usePipelineStore.getState().nodes
      const newNode = updatedNodes[updatedNodes.length - 1]
      if (newNode) {
        usePipelineStore.getState().updateNodeConfig(newNode.id, {
          source: 'local_path',
          local_path: result.model_path,
        })
      }

      toast.success(`Loaded epoch ${checkpoint.epoch} checkpoint as model node`)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load checkpoint'
      toast.error(msg)
    } finally {
      setLoadingModel(false)
    }
  }

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          gap: 8,
        }}
      >
        <Loader2 size={14} style={{ animation: 'spin 1s linear infinite', color: T.dim }} />
        <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
          Loading checkpoints...
        </span>
      </div>
    )
  }

  if (checkpoints.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
          No checkpoints saved for this run
        </span>
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.muted }}>
          Set checkpoint_interval {'>'} 0 in your training block to save checkpoints
        </span>
      </div>
    )
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div
        style={{
          padding: '8px 12px',
          borderBottom: `1px solid ${T.border}`,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xs,
            fontWeight: 700,
            color: T.text,
            letterSpacing: '0.08em',
          }}
        >
          CHECKPOINT TIMELINE
        </span>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {checkpoints.length} checkpoint{checkpoints.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Chart */}
      <div style={{ flex: 1, minHeight: 200, padding: '8px 4px 4px 4px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={lossData} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={T.border} />
            <XAxis
              dataKey="step"
              stroke={T.dim}
              tick={{ fill: T.dim, fontSize: 7, fontFamily: F }}
              label={{
                value: 'Step',
                position: 'insideBottom',
                offset: -2,
                fill: T.dim,
                fontSize: 7,
                fontFamily: F,
              }}
            />
            <YAxis
              stroke={T.dim}
              tick={{ fill: T.dim, fontSize: 7, fontFamily: F }}
              width={50}
              label={{
                value: 'Loss',
                angle: -90,
                position: 'insideLeft',
                fill: T.dim,
                fontSize: 7,
                fontFamily: F,
              }}
            />
            <Tooltip
              contentStyle={{
                background: T.surface2,
                border: `1px solid ${T.borderHi}`,
                fontFamily: F,
                fontSize: 7,
                color: T.sec,
                padding: '4px 8px',
              }}
              labelStyle={{ fontFamily: F, fontSize: 7, color: T.dim }}
            />
            <Line
              type="monotone"
              dataKey="loss"
              stroke={T.cyan}
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            {/* Checkpoint markers */}
            {checkpointMarkers.map((marker) => (
              <ReferenceDot
                key={marker.epoch}
                x={marker.step}
                y={marker.loss}
                r={selectedCheckpoint?.epoch === marker.epoch ? 6 : 4}
                fill={selectedCheckpoint?.epoch === marker.epoch ? T.orange : T.blue}
                stroke={selectedCheckpoint?.epoch === marker.epoch ? T.orange : T.blue}
                strokeWidth={2}
                style={{ cursor: 'pointer' }}
                onClick={() =>
                  setSelectedCheckpoint(
                    selectedCheckpoint?.epoch === marker.epoch ? null : checkpoints.find((c) => c.epoch === marker.epoch) || null
                  )
                }
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Checkpoint list */}
      <div
        style={{
          borderTop: `1px solid ${T.border}`,
          maxHeight: 180,
          overflowY: 'auto',
        }}
      >
        {checkpoints.map((ckpt) => {
          const isSelected = selectedCheckpoint?.epoch === ckpt.epoch
          return (
            <div
              key={ckpt.epoch}
              onClick={() => setSelectedCheckpoint(isSelected ? null : ckpt)}
              style={{
                padding: '6px 12px',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                borderBottom: `1px solid ${T.border}`,
                background: isSelected ? `${T.cyan}10` : 'transparent',
                cursor: 'pointer',
                transition: 'background 0.1s',
              }}
            >
              {/* Epoch badge */}
              <span
                style={{
                  fontFamily: F,
                  fontSize: FS.xs,
                  fontWeight: 700,
                  color: isSelected ? T.cyan : T.sec,
                  minWidth: 60,
                }}
              >
                Epoch {ckpt.epoch}
              </span>

              {/* Metrics */}
              <div style={{ display: 'flex', gap: 12, flex: 1 }}>
                {Object.entries(ckpt.metrics).map(([key, val]) => (
                  <span
                    key={key}
                    style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      color: T.dim,
                    }}
                  >
                    {key}: <span style={{ color: T.sec }}>{typeof val === 'number' ? val.toFixed(4) : val}</span>
                  </span>
                ))}
              </div>

              {/* Timestamp */}
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.muted }}>
                {new Date(ckpt.timestamp * 1000).toLocaleTimeString()}
              </span>

              {/* Load as model button */}
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  handleLoadAsModel(ckpt)
                }}
                disabled={loadingModel}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '2px 8px',
                  background: `${T.cyan}15`,
                  border: `1px solid ${T.cyan}40`,
                  color: T.cyan,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  cursor: loadingModel ? 'wait' : 'pointer',
                  opacity: loadingModel ? 0.5 : 1,
                  letterSpacing: '0.06em',
                  whiteSpace: 'nowrap',
                }}
              >
                <Download size={8} />
                LOAD AS MODEL
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
