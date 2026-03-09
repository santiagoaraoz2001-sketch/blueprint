import { useState, useRef, useEffect } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useNotificationStore, type Notification } from '@/stores/notificationStore'
import { Bell, CheckCheck, Trash2, CheckCircle2, XCircle, Info, AlertTriangle } from 'lucide-react'

const TYPE_ICON: Record<Notification['type'], { icon: React.ReactNode; color: string }> = {
  success: { icon: <CheckCircle2 size={10} />, color: T.green },
  error: { icon: <XCircle size={10} />, color: T.red },
  info: { icon: <Info size={10} />, color: T.blue },
  warning: { icon: <AlertTriangle size={10} />, color: T.amber },
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const secs = Math.floor(diff / 1000)
  if (secs < 60) return 'just now'
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export default function NotificationBell() {
  const { notifications, unreadCount, markRead, markAllRead, clearAll } = useNotificationStore()
  const [open, setOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  // Close panel on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div ref={panelRef} style={{ position: 'relative' }}>
      {/* Bell button */}
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: 'none',
          border: 'none',
          color: unreadCount > 0 ? T.cyan : T.dim,
          cursor: 'pointer',
          padding: '2px 4px',
          display: 'flex',
          alignItems: 'center',
          position: 'relative',
        }}
      >
        <Bell size={11} />
        {unreadCount > 0 && (
          <span
            style={{
              position: 'absolute',
              top: -2,
              right: -2,
              minWidth: 12,
              height: 12,
              borderRadius: 6,
              background: T.red,
              color: '#fff',
              fontFamily: F,
              fontSize: 5,
              fontWeight: 900,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '0 2px',
            }}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div
          style={{
            position: 'absolute',
            bottom: '100%',
            right: 0,
            width: 300,
            maxHeight: 360,
            background: T.surface2,
            border: `1px solid ${T.borderHi}`,
            boxShadow: `0 8px 32px ${T.shadow}`,
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
            marginBottom: 4,
          }}
        >
          {/* Panel header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '8px 10px',
              borderBottom: `1px solid ${T.border}`,
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
              NOTIFICATIONS
              {unreadCount > 0 && (
                <span style={{ color: T.dim, fontWeight: 400, marginLeft: 6 }}>
                  ({unreadCount} unread)
                </span>
              )}
            </span>
            <div style={{ display: 'flex', gap: 4 }}>
              {unreadCount > 0 && (
                <button
                  onClick={markAllRead}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: T.cyan,
                    cursor: 'pointer',
                    padding: 2,
                    display: 'flex',
                  }}
                  title="Mark all read"
                >
                  <CheckCheck size={11} />
                </button>
              )}
              {notifications.length > 0 && (
                <button
                  onClick={clearAll}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: T.dim,
                    cursor: 'pointer',
                    padding: 2,
                    display: 'flex',
                  }}
                  title="Clear all"
                >
                  <Trash2 size={11} />
                </button>
              )}
            </div>
          </div>

          {/* Notification list */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {notifications.length === 0 ? (
              <div
                style={{
                  padding: 24,
                  textAlign: 'center',
                  fontFamily: F,
                  fontSize: FS.xs,
                  color: T.dim,
                }}
              >
                No notifications
              </div>
            ) : (
              notifications.map((n) => {
                const typeInfo = TYPE_ICON[n.type]
                return (
                  <div
                    key={n.id}
                    onClick={() => markRead(n.id)}
                    style={{
                      display: 'flex',
                      gap: 8,
                      padding: '8px 10px',
                      borderBottom: `1px solid ${T.border}`,
                      cursor: 'pointer',
                      background: n.read ? 'transparent' : `${T.cyan}06`,
                      transition: 'background 0.1s',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = T.surface3
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = n.read ? 'transparent' : `${T.cyan}06`
                    }}
                  >
                    {/* Type icon */}
                    <div style={{ color: typeInfo.color, flexShrink: 0, paddingTop: 1 }}>
                      {typeInfo.icon}
                    </div>

                    {/* Content */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                        <span
                          style={{
                            fontFamily: F,
                            fontSize: FS.sm,
                            fontWeight: n.read ? 400 : 700,
                            color: T.text,
                          }}
                        >
                          {n.title}
                        </span>
                        {!n.read && (
                          <span
                            style={{
                              width: 4,
                              height: 4,
                              borderRadius: 2,
                              background: T.cyan,
                              flexShrink: 0,
                            }}
                          />
                        )}
                      </div>
                      <div
                        style={{
                          fontFamily: F,
                          fontSize: FS.xs,
                          color: T.sec,
                          lineHeight: 1.4,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {n.message}
                      </div>
                      <div
                        style={{
                          fontFamily: F,
                          fontSize: FS.xxs,
                          color: T.dim,
                          marginTop: 2,
                        }}
                      >
                        {relativeTime(n.timestamp)}
                      </div>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
