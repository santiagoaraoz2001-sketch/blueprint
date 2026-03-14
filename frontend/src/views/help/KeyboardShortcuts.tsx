import { T, F, FS } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import { Keyboard } from 'lucide-react'

const badge: React.CSSProperties = {
  display: 'inline-block',
  fontFamily: 'JetBrains Mono, monospace',
  fontSize: FS.xs,
  fontWeight: 600,
  background: T.surface1,
  border: `1px solid ${T.border}`,
  padding: '3px 8px',
  color: T.fg,
  minWidth: 28,
  textAlign: 'center',
}

const SHORTCUTS = [
  { keys: ['Cmd', 'K'], action: 'Open command palette' },
  { keys: ['Cmd', 'S'], action: 'Save current pipeline' },
  { keys: ['Cmd', 'Z'], action: 'Undo' },
  { keys: ['Cmd', 'Shift', 'Z'], action: 'Redo' },
  { keys: ['Cmd', 'E'], action: 'Export pipeline' },
  { keys: ['Cmd', 'I'], action: 'Import pipeline' },
  { keys: ['Cmd', 'G'], action: 'Open Block Generator' },
  { keys: ['Shift', 'R'], action: 'Re-run from selected node' },
  { keys: ['Delete'], action: 'Delete selected node/edge' },
  { keys: ['Escape'], action: 'Deselect / close panel / exit overlay' },
  { keys: ['Space'], action: 'Pan canvas (hold + drag)' },
  { keys: ['Cmd', '+'], action: 'Zoom in' },
  { keys: ['Cmd', '-'], action: 'Zoom out' },
  { keys: ['Cmd', '0'], action: 'Fit to screen' },
  { keys: ['Cmd', 'Shift', 'V'], action: 'Validate pipeline' },
]

export const KEYBOARD_SHORTCUTS_TEXT = `Keyboard Shortcuts. ${SHORTCUTS.map((s) => `${s.keys.join('+')} ${s.action}`).join('. ')}`

export default function KeyboardShortcuts() {
  return (
    <div>
      <SectionAnchor id="keyboard-shortcuts" title="Keyboard Shortcuts" level={1}>
        <Keyboard size={22} color={T.accent} />
      </SectionAnchor>

      <div
        style={{
          background: T.surface2,
          border: `1px solid ${T.borderHi}`,
          padding: 20,
        }}
      >
        {SHORTCUTS.map((s, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '8px 0',
              borderBottom: i < SHORTCUTS.length - 1 ? `1px solid ${T.border}` : 'none',
            }}
          >
            <div style={{ display: 'flex', gap: 4 }}>
              {s.keys.map((k, j) => (
                <span key={j}>
                  <span style={badge}>{k}</span>
                  {j < s.keys.length - 1 && (
                    <span
                      style={{
                        fontFamily: F,
                        fontSize: FS.xs,
                        color: T.dim,
                        margin: '0 2px',
                      }}
                    >
                      +
                    </span>
                  )}
                </span>
              ))}
            </div>
            <span
              style={{
                fontFamily: F,
                fontSize: FS.sm,
                color: T.sec,
              }}
            >
              {s.action}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
