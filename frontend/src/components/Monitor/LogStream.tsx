import { useEffect, useRef } from 'react'
import { useRunStore } from '@/stores/runStore'
import { T, F, FS } from '@/lib/design-tokens'

interface LogStreamProps {
  runId: string
}

export default function LogStream({ runId: _runId }: LogStreamProps) {
  const logs = useRunStore((s) => s.logs)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [logs.length])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        padding: '4px 12px', borderBottom: `1px solid ${T.border}`,
        fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.12em',
        textTransform: 'uppercase',
      }}>
        LOG STREAM
      </div>
      <div
        ref={containerRef}
        style={{
          flex: 1, overflow: 'auto', padding: '4px 12px',
          fontFamily: F, fontSize: FS.xxs, lineHeight: 1.6, color: T.sec,
          background: T.surface0,
        }}
      >
        {logs.length === 0 ? (
          <span style={{ color: T.dim }}>Waiting for logs...</span>
        ) : (
          logs.map((log, i) => (
            <div key={i} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              {log.startsWith('[metric]') ? (
                <span style={{ color: T.cyan }}>{log}</span>
              ) : log.startsWith('[output]') ? (
                <span style={{ color: T.green }}>{log}</span>
              ) : (
                log
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
