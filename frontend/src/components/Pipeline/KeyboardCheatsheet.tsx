import { useEffect, useRef } from 'react'
import { T, F, FS, DEPTH } from '@/lib/design-tokens'
import { X } from 'lucide-react'

const isMac = typeof navigator !== 'undefined' && navigator.platform.toUpperCase().indexOf('MAC') >= 0
const mod = isMac ? '\u2318' : 'Ctrl'
const shift = isMac ? '\u21E7' : 'Shift'

interface ShortcutEntry {
  keys: string
  description: string
}

const SHORTCUT_GROUPS: { title: string; shortcuts: ShortcutEntry[] }[] = [
  {
    title: 'General',
    shortcuts: [
      { keys: `${mod}+K`, description: 'Command palette' },
      { keys: `${mod}+S`, description: 'Save pipeline' },
      { keys: `${mod}+Z`, description: 'Undo' },
      { keys: `${mod}+${shift}+Z`, description: 'Redo' },
      { keys: `${mod}+Y`, description: 'Redo (alt)' },
      { keys: `${shift}+?`, description: 'Keyboard shortcuts' },
    ],
  },
  {
    title: 'Canvas',
    shortcuts: [
      { keys: `${mod}+A`, description: 'Select all nodes' },
      { keys: `${mod}+C`, description: 'Copy selected nodes' },
      { keys: `${mod}+V`, description: 'Paste nodes' },
      { keys: `${mod}+D`, description: 'Duplicate selected nodes' },
      { keys: 'Delete / Backspace', description: 'Delete selected nodes' },
      { keys: 'Escape', description: 'Deselect / close modal' },
      { keys: 'F', description: 'Fit view (frame all)' },
    ],
  },
  {
    title: 'Execution',
    shortcuts: [
      { keys: `${mod}+Enter`, description: 'Run pipeline' },
    ],
  },
]

interface Props {
  visible: boolean
  onClose: () => void
}

export default function KeyboardCheatsheet({ visible, onClose }: Props) {
  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!visible) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', handler, true)
    return () => window.removeEventListener('keydown', handler, true)
  }, [visible, onClose])

  if (!visible) return null

  return (
    <div
      ref={overlayRef}
      onClick={(e) => { if (e.target === overlayRef.current) onClose() }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10001,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: T.shadowHeavy,
      }}
    >
      <div
        style={{
          width: 520,
          maxHeight: '80vh',
          background: T.surface2,
          border: `1px solid ${T.borderHi}`,
          boxShadow: DEPTH.modal,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 20px',
          borderBottom: `1px solid ${T.border}`,
        }}>
          <span style={{
            fontFamily: F,
            fontSize: FS.lg,
            fontWeight: 700,
            color: T.text,
            letterSpacing: '0.04em',
          }}>
            KEYBOARD SHORTCUTS
          </span>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: T.dim,
              cursor: 'pointer',
              padding: 4,
              display: 'flex',
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflow: 'auto', padding: '12px 20px 20px' }}>
          {SHORTCUT_GROUPS.map((group) => (
            <div key={group.title} style={{ marginBottom: 18 }}>
              <div style={{
                fontFamily: F,
                fontSize: FS.xxs,
                fontWeight: 700,
                color: T.cyan,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                marginBottom: 8,
              }}>
                {group.title}
              </div>
              {group.shortcuts.map((s) => (
                <div
                  key={s.keys}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '5px 0',
                    borderBottom: `1px solid ${T.border}`,
                  }}
                >
                  <span style={{
                    fontFamily: F,
                    fontSize: FS.sm,
                    color: T.sec,
                  }}>
                    {s.description}
                  </span>
                  <kbd style={{
                    fontFamily: "'JetBrains Mono','SF Mono','Fira Code',monospace",
                    fontSize: FS.xxs,
                    color: T.dim,
                    background: T.surface4,
                    border: `1px solid ${T.border}`,
                    padding: '2px 8px',
                    letterSpacing: '0.06em',
                    whiteSpace: 'nowrap',
                  }}>
                    {s.keys}
                  </kbd>
                </div>
              ))}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div style={{
          padding: '8px 20px',
          borderTop: `1px solid ${T.border}`,
          display: 'flex',
          justifyContent: 'center',
        }}>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            Press Esc to close
          </span>
        </div>
      </div>
    </div>
  )
}
