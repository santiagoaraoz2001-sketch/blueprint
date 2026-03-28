/**
 * ValidationEdge — custom React Flow edge that renders with a red dashed stroke
 * when the backend validation store reports a type mismatch on this edge.
 *
 * Falls back to the standard smoothstep edge rendering for valid edges.
 */

import { memo } from 'react'
import {
  getSmoothStepPath,
  BaseEdge,
  type EdgeProps,
} from '@xyflow/react'
import { useValidationStore } from '@/stores/validationStore'
import { T } from '@/lib/design-tokens'

function ValidationEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  ...rest
}: EdgeProps) {
  const hasError = useValidationStore((s) => !!s.edgeErrors[id])

  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  })

  const errorStyle = hasError
    ? {
        ...style,
        stroke: 'var(--color-error, #EF5350)',
        strokeWidth: 2.5,
        strokeDasharray: '6 3',
        animation: undefined as string | undefined,
      }
    : style

  return (
    <BaseEdge
      id={id}
      path={edgePath}
      style={errorStyle}
      markerEnd={markerEnd}
    />
  )
}

export default memo(ValidationEdge)
