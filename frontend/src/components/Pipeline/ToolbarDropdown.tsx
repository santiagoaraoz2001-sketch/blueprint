import { useState, useRef, useEffect } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { ChevronDown } from 'lucide-react'

interface DropdownItem {
  label: string
  icon?: React.ReactNode
  onClick: () => void
  color?: string
  separator?: boolean
  disabled?: boolean
  tooltip?: string
}

interface ToolbarDropdownProps {
  label: string
  icon?: React.ReactNode
  items: DropdownItem[]
  style?: React.CSSProperties
}

const btnBase: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 4,
  padding: '3px 8px',
  background: 'transparent',
  border: `1px solid ${T.border}`,
  color: T.dim,
  fontFamily: F,
  fontSize: FS.xs,
  letterSpacing: '0.08em',
  cursor: 'pointer',
  transition: 'all 0.12s',
  whiteSpace: 'nowrap' as const,
}

export default function ToolbarDropdown({ label, icon, items, style }: ToolbarDropdownProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    window.addEventListener('mousedown', handler)
    return () => window.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(!open)}
        style={{ ...btnBase, ...style }}
      >
        {icon}
        {label}
        <ChevronDown size={8} style={{
          transform: open ? 'rotate(180deg)' : 'none',
          transition: 'transform 0.15s',
        }} />
      </button>

      {open && (
        <div style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          marginTop: 4,
          minWidth: 180,
          background: T.surface2,
          border: `1px solid ${T.borderHi}`,
          borderRadius: 6,
          boxShadow: `0 8px 24px ${T.shadow}`,
          zIndex: 200,
          overflow: 'hidden',
        }}>
          {items.map((item, i) => (
            <div key={i}>
              {item.separator && i > 0 && (
                <div style={{ height: 1, background: T.border, margin: '2px 0' }} />
              )}
              <button
                onClick={item.disabled ? undefined : () => { item.onClick(); setOpen(false) }}
                disabled={item.disabled}
                title={item.disabled ? item.tooltip : undefined}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  width: '100%',
                  padding: '7px 12px',
                  background: 'transparent',
                  border: 'none',
                  color: item.disabled ? T.dim : (item.color || T.sec),
                  fontFamily: F,
                  fontSize: FS.xs,
                  cursor: item.disabled ? 'default' : 'pointer',
                  textAlign: 'left',
                  transition: 'background 0.1s',
                  opacity: item.disabled ? 0.4 : 1,
                }}
                onMouseEnter={(e) => { if (!item.disabled) e.currentTarget.style.background = T.surface4 }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
              >
                {item.icon}
                {item.label}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
