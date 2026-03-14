import { T, F, FS } from '@/lib/design-tokens'
import { Link2, Unlink } from 'lucide-react'
import { useState } from 'react'

interface InheritedFieldBadgeProps {
  sourceName: string
  isOverridden: boolean
  onOverride: () => void
  onResetToInherited: () => void
}

export default function InheritedFieldBadge({
  sourceName,
  isOverridden,
  onOverride,
  onResetToInherited,
}: InheritedFieldBadgeProps) {
  const [hovered, setHovered] = useState(false)

  if (isOverridden) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          marginLeft: 'auto',
        }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.orange,
            fontWeight: 400,
            fontStyle: 'normal',
            whiteSpace: 'nowrap',
          }}
        >
          Overridden
        </span>
        {hovered && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onResetToInherited()
            }}
            title={`Reset to inherited value from ${sourceName}`}
            style={{
              background: 'none',
              border: 'none',
              color: T.blue,
              cursor: 'pointer',
              padding: 0,
              display: 'flex',
              alignItems: 'center',
              gap: 3,
              fontFamily: F,
              fontSize: FS.xxs,
              fontWeight: 400,
              whiteSpace: 'nowrap',
            }}
          >
            <Link2 size={9} />
            reset
          </button>
        )}
      </div>
    )
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        marginLeft: 'auto',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <span
        style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.blue,
          fontWeight: 400,
          fontStyle: 'normal',
          whiteSpace: 'nowrap',
          opacity: 0.7,
        }}
      >
        from {sourceName}
      </span>
      {hovered && (
        <button
          onClick={(e) => {
            e.stopPropagation()
            onOverride()
          }}
          title="Override this inherited value"
          style={{
            background: 'none',
            border: 'none',
            color: T.orange,
            cursor: 'pointer',
            padding: 0,
            display: 'flex',
            alignItems: 'center',
            gap: 3,
            fontFamily: F,
            fontSize: FS.xxs,
            fontWeight: 400,
            whiteSpace: 'nowrap',
          }}
        >
          <Unlink size={9} />
          override
        </button>
      )}
    </div>
  )
}
