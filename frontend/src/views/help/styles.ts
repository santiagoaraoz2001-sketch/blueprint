import { T, F, FS } from '@/lib/design-tokens'

export const helpCard: React.CSSProperties = {
  padding: 20,
  background: T.surface2,
  border: `1px solid ${T.borderHi}`,
  marginBottom: 14,
}

export const helpBody: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.sm,
  color: T.sec,
  lineHeight: 1.7,
}

export const helpTip: React.CSSProperties = {
  padding: '10px 14px',
  background: T.surface1,
  borderLeft: `3px solid ${T.accent}`,
  fontFamily: F,
  fontSize: FS.xs,
  color: T.sec,
  lineHeight: 1.6,
  marginTop: 10,
}

export const helpStepList: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.sm,
  color: T.sec,
  lineHeight: 1.8,
  paddingLeft: 20,
  margin: '8px 0',
}

export const helpCode: React.CSSProperties = {
  fontFamily: 'JetBrains Mono, monospace',
  fontSize: FS.xs,
  background: T.surface1,
  padding: '2px 6px',
  color: T.accent,
}

export const helpCodeBlock: React.CSSProperties = {
  fontFamily: 'JetBrains Mono, monospace',
  fontSize: FS.xs,
  color: T.accent,
  background: T.surface1,
  padding: '10px 14px',
  lineHeight: 1.6,
  marginTop: 8,
  marginBottom: 8,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-all',
}
