import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { T, F, FD, FS, getTheme } from '@/lib/design-tokens'
import { playSound } from '@/lib/audio'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { FolderOpen, RefreshCw, ExternalLink, Sliders } from 'lucide-react'
import {
  useSettingsStore,
  FONT_MAP,
  FONT_LABELS,
  FONT_SIZE_LABELS,
  type FontChoice,
  type FontSizeScale,
  type ThemeMode,
  type AccentColor,
} from '@/stores/settingsStore'
import { useAgentStore, type LLMProvider } from '@/stores/agentStore'
import { PROVIDERS } from '@/lib/llm-adapters'

/* ------------------------------------------------------------------ */
/*  Accent Color Options                                              */
/* ------------------------------------------------------------------ */

const ACCENT_COLORS: { id: AccentColor; label: string; token: string }[] = [
  { id: 'cyan', label: 'Cyan', token: 'cyan' },
  { id: 'orange', label: 'Orange', token: 'orange' },
  { id: 'green', label: 'Green', token: 'green' },
  { id: 'blue', label: 'Blue', token: 'blue' },
  { id: 'purple', label: 'Purple', token: 'purple' },
  { id: 'pink', label: 'Pink', token: 'pink' },
]

/* ------------------------------------------------------------------ */
/*  Shared styles                                                     */
/* ------------------------------------------------------------------ */

const sectionHeader: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.xxs,
  fontWeight: 900,
  letterSpacing: '0.14em',
  textTransform: 'uppercase',
  color: T.dim,
  margin: 0,
  marginBottom: 12,
}

const labelStyle: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.xxs,
  color: T.dim,
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  display: 'block',
  marginBottom: 4,
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '5px 8px',
  background: T.surface4,
  border: `1px solid ${T.border}`,
  color: T.text,
  fontFamily: F,
  fontSize: FS.sm,
  outline: 'none',
  borderRadius: 0,
  appearance: 'none',
  WebkitAppearance: 'none',
}

const descStyle: React.CSSProperties = {
  fontFamily: F,
  fontSize: FS.xxs,
  color: T.dim,
  marginTop: 3,
  lineHeight: 1.5,
}

const sectionContainer: React.CSSProperties = {
  padding: 14,
  background: T.surface1,
  border: `1px solid ${T.border}`,
  marginBottom: 16,
}

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
}

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' as const } },
}

/* ------------------------------------------------------------------ */
/*  Toggle button (ON/OFF) — matches BlockConfig boolean style        */
/* ------------------------------------------------------------------ */

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      style={{
        ...inputStyle,
        width: 'auto',
        textAlign: 'left',
        color: value ? T.cyan : T.dim,
        cursor: 'pointer',
        fontWeight: 900,
        letterSpacing: '0.1em',
        padding: '5px 12px',
      }}
    >
      {value ? 'ON' : 'OFF'}
    </button>
  )
}

/* ------------------------------------------------------------------ */
/*  Theme preview card                                                */
/* ------------------------------------------------------------------ */

function ThemePreviewCard({
  mode,
  active,
  onClick,
}: {
  mode: ThemeMode
  active: boolean
  onClick: () => void
}) {
  const tokens = getTheme(mode)

  return (
    <button
      onClick={onClick}
      style={{
        flex: 1,
        padding: 0,
        border: active ? `1px solid ${T.cyan}` : `1px solid ${T.border}`,
        background: 'transparent',
        cursor: 'pointer',
        outline: 'none',
        boxShadow: active ? `0 0 8px ${T.cyan}30` : 'none',
        transition: 'all 0.15s ease',
        borderRadius: 0,
      }}
    >
      {/* Mini app mockup */}
      <div style={{ background: tokens.bg, padding: 8, height: 80 }}>
        {/* Fake topbar */}
        <div
          style={{
            height: 8,
            background: tokens.surface3,
            borderBottom: `1px solid ${tokens.border}`,
            marginBottom: 6,
            display: 'flex',
            alignItems: 'center',
            paddingLeft: 3,
            gap: 2,
          }}
        >
          <div style={{ width: 3, height: 3, borderRadius: '50%', background: tokens.cyan }} />
          <div
            style={{
              width: 16,
              height: 2,
              background: tokens.dim,
              opacity: 0.5,
            }}
          />
        </div>

        {/* Content area */}
        <div style={{ display: 'flex', gap: 4 }}>
          {/* Sidebar */}
          <div
            style={{
              width: 16,
              background: tokens.surface1,
              border: `1px solid ${tokens.border}`,
              display: 'flex',
              flexDirection: 'column',
              gap: 3,
              padding: 2,
            }}
          >
            <div style={{ height: 2, background: tokens.cyan, opacity: 0.6 }} />
            <div style={{ height: 2, background: tokens.dim, opacity: 0.3 }} />
            <div style={{ height: 2, background: tokens.dim, opacity: 0.3 }} />
          </div>

          {/* Main */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 3 }}>
            <div
              style={{
                height: 3,
                width: '60%',
                background: tokens.text,
                opacity: 0.3,
              }}
            />
            <div
              style={{
                height: 20,
                background: tokens.surface2,
                border: `1px solid ${tokens.border}`,
              }}
            />
            <div style={{ display: 'flex', gap: 3 }}>
              <div
                style={{
                  flex: 1,
                  height: 10,
                  background: tokens.surface3,
                  border: `1px solid ${tokens.border}`,
                }}
              />
              <div
                style={{
                  flex: 1,
                  height: 10,
                  background: tokens.surface3,
                  border: `1px solid ${tokens.border}`,
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Label */}
      <div
        style={{
          padding: '5px 0',
          background: active ? `${T.cyan}10` : T.surface2,
          borderTop: `1px solid ${active ? T.cyan : T.border}`,
        }}
      >
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            fontWeight: 900,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: active ? T.cyan : T.dim,
          }}
        >
          {mode}
        </span>
      </div>
    </button>
  )
}

/* ------------------------------------------------------------------ */
/*  Provider card — displays one LLM provider as a selectable tile     */
/* ------------------------------------------------------------------ */

const ALL_PROVIDERS: { id: LLMProvider; label: string; requiresKey: boolean }[] = [
  ...PROVIDERS.map((p) => ({ id: p.id as LLMProvider, label: p.label, requiresKey: p.requiresKey })),
  { id: 'manual', label: 'Manual', requiresKey: false },
]

function ProviderCard({
  provider,
  active,
  connected,
  onClick,
}: {
  provider: { id: string; label: string; requiresKey: boolean }
  active: boolean
  connected: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      style={{
        flex: '1 1 0',
        minWidth: 80,
        padding: '8px 6px',
        border: active ? `1px solid ${T.cyan}` : `1px solid ${T.border}`,
        background: active ? `${T.cyan}08` : T.surface2,
        cursor: 'pointer',
        outline: 'none',
        boxShadow: active ? `0 0 8px ${T.cyan}30` : 'none',
        transition: 'all 0.15s ease',
        borderRadius: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 4,
      }}
    >
      {/* Status dot */}
      <div
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: active && connected ? T.green : T.dim,
          opacity: active && connected ? 1 : 0.5,
          transition: 'all 0.2s ease',
        }}
      />
      {/* Provider name */}
      <span
        style={{
          fontFamily: F,
          fontSize: FS.xxs,
          fontWeight: 900,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          color: active ? T.cyan : T.dim,
        }}
      >
        {provider.label}
      </span>
      {/* Requires key indicator */}
      {provider.requiresKey && (
        <span
          style={{
            fontFamily: F,
            fontSize: 4.5,
            color: T.dim,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          API KEY
        </span>
      )}
    </button>
  )
}

/* ------------------------------------------------------------------ */
/*  LLM Providers section                                              */
/* ------------------------------------------------------------------ */

function LlmProvidersSection() {
  const {
    provider,
    endpoint,
    model,
    isConnected,
    availableModels,
    setProvider,
    setEndpoint,
    setModel,
    testConnection,
    fetchModels,
  } = useAgentStore()

  const { getApiKey, setApiKey } = useSettingsStore()

  const [showKey, setShowKey] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState<'idle' | 'testing' | 'success' | 'failed'>('idle')
  const [isFetchingModels, setIsFetchingModels] = useState(false)

  const currentProviderMeta = ALL_PROVIDERS.find((p) => p.id === provider)
  const needsApiKey = currentProviderMeta?.requiresKey ?? false
  const isLocal = provider === 'ollama' || provider === 'mlx'

  const handleTestConnection = async () => {
    setConnectionStatus('testing')
    const ok = await testConnection()
    setConnectionStatus(ok ? 'success' : 'failed')
  }

  const handleFetchModels = async () => {
    setIsFetchingModels(true)
    await fetchModels()
    setIsFetchingModels(false)
  }

  const handleProviderChange = (id: LLMProvider) => {
    setProvider(id)
    setConnectionStatus('idle')
  }

  return (
    <motion.div variants={fadeUp} style={sectionContainer}>
      <h2 style={sectionHeader}>LLM PROVIDERS</h2>

      {/* ── Provider selector cards ─────────────────────── */}
      <div style={{ marginBottom: 14 }}>
        <label style={labelStyle}>PROVIDER</label>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {ALL_PROVIDERS.map((p) => (
            <ProviderCard
              key={p.id}
              provider={p}
              active={provider === p.id}
              connected={provider === p.id && isConnected}
              onClick={() => handleProviderChange(p.id)}
            />
          ))}
        </div>
      </div>

      {/* ── API Key input (only for providers that need it) ── */}
      {needsApiKey && (
        <div style={{ marginBottom: 14 }}>
          <label style={labelStyle}>API KEY</label>
          <div style={{ display: 'flex', gap: 6 }}>
            <div style={{ flex: 1, position: 'relative' }}>
              <input
                type={showKey ? 'text' : 'password'}
                value={getApiKey(provider)}
                onChange={(e) => setApiKey(provider, e.target.value)}
                placeholder={`Enter ${currentProviderMeta?.label ?? provider} API key`}
                style={{ ...inputStyle, paddingRight: 30 }}
              />
              <button
                onClick={() => setShowKey((v) => !v)}
                style={{
                  position: 'absolute',
                  right: 4,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  color: T.dim,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  cursor: 'pointer',
                  padding: '2px 4px',
                  letterSpacing: '0.08em',
                }}
              >
                {showKey ? 'HIDE' : 'SHOW'}
              </button>
            </div>
            <button
              onClick={handleTestConnection}
              disabled={connectionStatus === 'testing'}
              style={{
                ...inputStyle,
                width: 'auto',
                cursor: connectionStatus === 'testing' ? 'wait' : 'pointer',
                fontWeight: 900,
                letterSpacing: '0.1em',
                padding: '5px 12px',
                color: T.cyan,
                whiteSpace: 'nowrap',
              }}
            >
              {connectionStatus === 'testing' ? 'TESTING...' : 'TEST CONNECTION'}
            </button>
          </div>
          {connectionStatus === 'success' && (
            <span style={{ ...descStyle, color: T.green, fontWeight: 700 }}>Connected</span>
          )}
          {connectionStatus === 'failed' && (
            <span style={{ ...descStyle, color: T.red, fontWeight: 700 }}>Failed</span>
          )}
        </div>
      )}

      {/* ── Endpoint input ──────────────────────────────── */}
      <div style={{ marginBottom: 14 }}>
        <label style={labelStyle}>ENDPOINT</label>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            type="text"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            style={{ ...inputStyle, flex: 1 }}
          />
          {isLocal && (
            <div
              title={isConnected ? 'Local server reachable' : 'Local server not connected'}
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: isConnected ? T.green : T.dim,
                flexShrink: 0,
                transition: 'background 0.2s ease',
              }}
            />
          )}
        </div>
        <p style={descStyle}>
          {isLocal
            ? 'Local server endpoint — ensure the service is running'
            : 'API endpoint for the selected provider'}
        </p>
      </div>

      {/* ── Model selector ──────────────────────────────── */}
      <div>
        <label style={labelStyle}>MODEL</label>
        <div style={{ display: 'flex', gap: 6 }}>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            style={{ ...inputStyle, flex: 1 }}
          >
            {availableModels.length === 0 && (
              <option value="">— no models loaded —</option>
            )}
            {availableModels.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <button
            onClick={handleFetchModels}
            disabled={isFetchingModels}
            style={{
              ...inputStyle,
              width: 'auto',
              cursor: isFetchingModels ? 'wait' : 'pointer',
              fontWeight: 900,
              letterSpacing: '0.1em',
              padding: '5px 12px',
              color: T.cyan,
              whiteSpace: 'nowrap',
            }}
          >
            {isFetchingModels ? 'LOADING...' : 'REFRESH MODELS'}
          </button>
        </div>
      </div>
    </motion.div>
  )
}

/* ------------------------------------------------------------------ */
/*  Mode card — card-style selector for UI mode                        */
/* ------------------------------------------------------------------ */

function ModeCard({
  active,
  onClick,
  title,
  description,
  features,
}: {
  active: boolean
  onClick: () => void
  title: string
  description: string
  features: string[]
}) {
  return (
    <button
      onClick={onClick}
      style={{
        flex: 1,
        padding: '14px 16px',
        border: active ? `1px solid ${T.cyan}` : `1px solid ${T.border}`,
        background: active ? `${T.cyan}08` : T.surface2,
        cursor: 'pointer',
        outline: 'none',
        boxShadow: active ? `0 0 8px ${T.cyan}30` : 'none',
        transition: 'all 0.15s ease',
        borderRadius: 0,
        textAlign: 'left',
      }}
    >
      <div style={{
        fontFamily: F, fontSize: FS.md, fontWeight: 900,
        letterSpacing: '0.1em', textTransform: 'uppercase',
        color: active ? T.cyan : T.dim, marginBottom: 6,
      }}>
        {title}
      </div>
      <div style={{
        fontFamily: F, fontSize: FS.xs, color: T.sec,
        lineHeight: 1.5, marginBottom: 8,
      }}>
        {description}
      </div>
      <ul style={{ margin: 0, paddingLeft: 16 }}>
        {features.map((f, i) => (
          <li key={i} style={{
            fontFamily: F, fontSize: FS.xxs, color: T.dim,
            lineHeight: 1.6,
          }}>
            {f}
          </li>
        ))}
      </ul>
    </button>
  )
}

/* ------------------------------------------------------------------ */
/*  SettingsView                                                       */
/* ------------------------------------------------------------------ */

export default function SettingsView() {
  const {
    theme, accentColor, font, fontSize, demoMode, autoSaveInterval,
    setTheme, setAccentColor, setFont, setFontSize, setDemoMode, setAutoSaveInterval,
    uiMode, setUiMode,
    audioAlertsEnabled, audioVolume, audioOnStepComplete, audioOnPipelineComplete, audioOnError,
    setAudioAlertsEnabled, setAudioVolume, setAudioOnStepComplete, setAudioOnPipelineComplete, setAudioOnError,
  } = useSettingsStore()

  const intervalOptions = [
    { label: '3s', value: 3000 },
    { label: '5s', value: 5000 },
    { label: '10s', value: 10000 },
    { label: '30s', value: 30000 },
    { label: 'OFF', value: 0 },
  ]

  return (
    <div style={{ padding: 20, height: '100%', overflowY: 'auto' }}>
      <div style={{ maxWidth: 600, margin: '0 auto' }}>
        {/* Page title */}
        <div style={{ marginBottom: 20 }}>
          <h1
            style={{
              fontFamily: FD,
              fontSize: FS.h2,
              fontWeight: 700,
              color: T.text,
              margin: 0,
              letterSpacing: '0.04em',
            }}
          >
            SETTINGS
          </h1>
          <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, margin: '4px 0 0' }}>
            Application preferences and configuration
          </p>
        </div>

        <motion.div variants={stagger} initial="hidden" animate="show">
          {/* ── UI MODE ────────────────────────────────────── */}
          <motion.div variants={fadeUp} style={sectionContainer}>
            <h2 style={sectionHeader}>UI MODE</h2>
            <div style={{ display: 'flex', gap: 10 }}>
              <ModeCard
                active={uiMode === 'simple'}
                onClick={() => setUiMode('simple')}
                title="Simple"
                description="Perfect for getting started. Core ML workflow: load data, train, evaluate."
                features={[
                  '6 core block categories',
                  'Flat config (no inheritance)',
                  'Essential navigation only',
                ]}
              />
              <ModeCard
                active={uiMode === 'professional'}
                onClick={() => setUiMode('professional')}
                title="Professional"
                description="Full power. Plugins, export connectors, advanced monitoring, paper writing."
                features={[
                  'All 11 block categories',
                  'Config inheritance from upstream',
                  'Paper writing, Workshop, Custom blocks',
                ]}
              />
            </div>
          </motion.div>

          {/* ── APPEARANCE ────────────────────────────────── */}
          <motion.div variants={fadeUp} style={sectionContainer}>
            <h2 style={sectionHeader}>APPEARANCE</h2>

            {/* Theme toggle */}
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>THEME</label>
              <div style={{ display: 'flex', gap: 10 }}>
                <ThemePreviewCard
                  mode="dark"
                  active={theme === 'dark'}
                  onClick={() => setTheme('dark')}
                />
                <ThemePreviewCard
                  mode="light"
                  active={theme === 'light'}
                  onClick={() => setTheme('light')}
                />
                {/* System preference — auto-detect */}
                <button
                  onClick={() => setTheme('system')}
                  style={{
                    flex: 1,
                    padding: 0,
                    border: theme === 'system' ? `1px solid ${T.cyan}` : `1px solid ${T.border}`,
                    background: 'transparent',
                    cursor: 'pointer',
                    outline: 'none',
                    boxShadow: theme === 'system' ? `0 0 8px ${T.cyan}30` : 'none',
                    transition: 'all 0.15s ease',
                    borderRadius: 0,
                    display: 'flex',
                    flexDirection: 'column',
                  }}
                >
                  <div style={{ background: T.bg, padding: 8, height: 80, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <span style={{ fontFamily: F, fontSize: FS.lg, color: T.dim }}>AUTO</span>
                  </div>
                  <div
                    style={{
                      padding: '5px 0',
                      background: theme === 'system' ? `${T.cyan}10` : T.surface2,
                      borderTop: `1px solid ${theme === 'system' ? T.cyan : T.border}`,
                    }}
                  >
                    <span
                      style={{
                        fontFamily: F,
                        fontSize: FS.xxs,
                        fontWeight: 900,
                        letterSpacing: '0.12em',
                        textTransform: 'uppercase',
                        color: theme === 'system' ? T.cyan : T.dim,
                      }}
                    >
                      SYSTEM
                    </span>
                  </div>
                </button>
              </div>
            </div>

            {/* Accent Color selector */}
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>ACCENT COLOR</label>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                {ACCENT_COLORS.map((color) => {
                  const active = accentColor === color.id
                  const resolvedMode = theme === 'system'
                    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
                    : theme
                  const hex = (getTheme(resolvedMode) as any)[color.token]
                  return (
                    <button
                      key={color.id}
                      onClick={() => setAccentColor(color.id)}
                      title={color.label}
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: '50%',
                        background: hex,
                        border: active ? `2px solid ${T.text}` : `2px solid transparent`,
                        cursor: 'pointer',
                        padding: 0,
                        outline: 'none',
                        boxShadow: active ? `0 0 12px ${hex}60` : 'none',
                        transition: 'all 0.15s ease',
                      }}
                    />
                  )
                })}
              </div>
            </div>

            {/* Font selector */}
            <div>
              <label style={labelStyle}>FONT</label>
              <select
                value={font}
                onChange={(e) => setFont(e.target.value as FontChoice)}
                style={inputStyle}
              >
                {(Object.keys(FONT_LABELS) as FontChoice[]).map((key) => (
                  <option key={key} value={key}>
                    {FONT_LABELS[key]}
                  </option>
                ))}
              </select>

              {/* Live preview */}
              <div
                style={{
                  marginTop: 8,
                  padding: '8px 10px',
                  background: T.surface2,
                  border: `1px solid ${T.border}`,
                }}
              >
                <span
                  style={{
                    fontFamily: FONT_MAP[font],
                    fontSize: FS.md,
                    color: T.sec,
                    lineHeight: 1.6,
                  }}
                >
                  The quick brown fox jumps over the lazy dog
                </span>
                <br />
                <span
                  style={{
                    fontFamily: FONT_MAP[font],
                    fontSize: FS.sm,
                    color: T.dim,
                    lineHeight: 1.6,
                  }}
                >
                  0123456789 {'{'} fn main() {'=> {}'} {'}'} &lt;Component /&gt;
                </span>
              </div>
            </div>

            {/* Font size selector */}
            <div style={{ marginTop: 14 }}>
              <label style={labelStyle}>FONT SIZE</label>
              <div style={{ display: 'flex', gap: 6 }}>
                {(Object.keys(FONT_SIZE_LABELS) as FontSizeScale[]).map((key) => (
                  <button
                    key={key}
                    onClick={() => setFontSize(key)}
                    style={{
                      flex: 1,
                      padding: '6px 8px',
                      border: fontSize === key ? `1px solid ${T.cyan}` : `1px solid ${T.border}`,
                      background: fontSize === key ? `${T.cyan}08` : T.surface2,
                      cursor: 'pointer',
                      outline: 'none',
                      boxShadow: fontSize === key ? `0 0 8px ${T.cyan}30` : 'none',
                      transition: 'all 0.15s ease',
                      borderRadius: 0,
                    }}
                  >
                    <span
                      style={{
                        fontFamily: F,
                        fontSize: FS.xxs,
                        fontWeight: 900,
                        letterSpacing: '0.1em',
                        textTransform: 'uppercase',
                        color: fontSize === key ? T.cyan : T.dim,
                      }}
                    >
                      {FONT_SIZE_LABELS[key]}
                    </span>
                  </button>
                ))}
              </div>
              <p style={descStyle}>Scales all text across the application</p>
            </div>
          </motion.div>

          {/* ── WORKFLOW ──────────────────────────────────── */}
          <motion.div variants={fadeUp} style={sectionContainer}>
            <h2 style={sectionHeader}>WORKFLOW</h2>

            {/* Auto-save interval */}
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>AUTO-SAVE INTERVAL</label>
              <select
                value={autoSaveInterval}
                onChange={(e) => setAutoSaveInterval(Number(e.target.value))}
                style={inputStyle}
              >
                {intervalOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Demo mode */}
            <div>
              <label style={labelStyle}>DEMO MODE</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Toggle value={demoMode} onChange={setDemoMode} />
                <span style={descStyle}>Load sample data without backend connection</span>
              </div>
            </div>
          </motion.div>

          {/* ── WORKSPACE ──────────────────────────────────── */}
          <WorkspaceSection />

          {/* ── AUDIO ALERTS ──────────────────────────────── */}
          <motion.div variants={fadeUp} style={sectionContainer}>
            <h2 style={sectionHeader}>AUDIO ALERTS</h2>

            <div>
              <label style={labelStyle}>ENABLE AUDIO</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Toggle value={audioAlertsEnabled} onChange={setAudioAlertsEnabled} />
                <span style={descStyle}>Play sounds for pipeline events</span>
              </div>
            </div>

            {audioAlertsEnabled && (
              <>
                <div style={{ marginTop: 16 }}>
                  <label style={labelStyle}>VOLUME</label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={audioVolume}
                      onChange={(e) => setAudioVolume(parseFloat(e.target.value))}
                      style={{ flex: 1, accentColor: T.cyan }}
                    />
                    <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, minWidth: 30 }}>
                      {Math.round(audioVolume * 100)}%
                    </span>
                  </div>
                </div>

                <div style={{ marginTop: 16 }}>
                  <label style={labelStyle}>STEP COMPLETE</label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Toggle value={audioOnStepComplete} onChange={setAudioOnStepComplete} />
                    <span style={descStyle}>Chime when a block finishes</span>
                  </div>
                </div>

                <div style={{ marginTop: 12 }}>
                  <label style={labelStyle}>PIPELINE COMPLETE</label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Toggle value={audioOnPipelineComplete} onChange={setAudioOnPipelineComplete} />
                    <span style={descStyle}>Fanfare when pipeline run completes</span>
                  </div>
                </div>

                <div style={{ marginTop: 12 }}>
                  <label style={labelStyle}>ERROR</label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Toggle value={audioOnError} onChange={setAudioOnError} />
                    <span style={descStyle}>Alert sound on block or run failure</span>
                  </div>
                </div>

                <div style={{ marginTop: 16 }}>
                  <button
                    onClick={() => playSound('notification')}
                    style={{
                      padding: '6px 14px',
                      background: `${T.cyan}14`,
                      border: `1px solid ${T.cyan}33`,
                      borderRadius: 4,
                      color: T.cyan,
                      fontFamily: F,
                      fontSize: FS.xs,
                      letterSpacing: '0.06em',
                      cursor: 'pointer',
                    }}
                  >
                    TEST SOUND
                  </button>
                </div>
              </>
            )}
          </motion.div>

          {/* ── LLM PROVIDERS ─────────────────────────────── */}
          <LlmProvidersSection />

          {/* ── ABOUT ─────────────────────────────────────── */}
          <motion.div variants={fadeUp} style={sectionContainer}>
            <h2 style={sectionHeader}>ABOUT</h2>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div>
                <label style={labelStyle}>VERSION</label>
                <span
                  style={{
                    fontFamily: F,
                    fontSize: FS.md,
                    color: T.text,
                    fontWeight: 700,
                  }}
                >
                  v0.2.2
                </span>
              </div>

              <div>
                <label style={labelStyle}>PRODUCT</label>
                <span
                  style={{
                    fontFamily: FD,
                    fontSize: FS.lg,
                    color: T.text,
                    fontWeight: 700,
                    letterSpacing: '0.06em',
                  }}
                >
                  SPECIFIC LABS BLUEPRINT
                </span>
              </div>

              <div>
                <label style={labelStyle}>DESCRIPTION</label>
                <span
                  style={{
                    fontFamily: F,
                    fontSize: FS.sm,
                    color: T.sec,
                    lineHeight: 1.5,
                  }}
                >
                  Local-first ML experiment workbench
                </span>
              </div>
            </div>
          </motion.div>
        </motion.div>
      </div>
    </div>
  )
}

/* ── Workspace Section ──────────────────────────────────────────── */

function WorkspaceSection() {
  const { settings, status, fetchSettings, updateSettings, fetchStatus, openInFinder, initialize } = useWorkspaceStore()
  const [browsing, setBrowsing] = useState(false)
  const [showWorkspaceConfig, setShowWorkspaceConfig] = useState(false)

  useEffect(() => {
    fetchSettings()
    fetchStatus()
  }, [fetchSettings, fetchStatus])

  const handleBrowse = async () => {
    if (browsing) return
    setBrowsing(true)
    try {
      let selectedPath: string | null = null
      if ((window as any).blueprint?.selectDirectory) {
        selectedPath = await (window as any).blueprint.selectDirectory({
          title: 'Select Workspace Folder',
          defaultPath: settings.root_path || undefined,
        })
      } else {
        const res = await fetch('/api/system/browse', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: 'directory', title: 'Select Workspace Folder', default_path: settings.root_path || '' }),
        })
        const data = await res.json()
        selectedPath = data.path
      }
      if (selectedPath) {
        await updateSettings({ root_path: selectedPath })
      }
    } catch {
      // Silently handle errors
    } finally {
      setBrowsing(false)
    }
  }

  const isConfigured = !!settings.root_path

  return (
    <motion.div variants={fadeUp} style={sectionContainer}>
      <h2 style={sectionHeader}>WORKSPACE</h2>

      {/* Folder Location */}
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>FOLDER LOCATION</label>
        <div style={{ display: 'flex', gap: 6, alignItems: 'stretch' }}>
          <div style={{
            ...inputStyle,
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            color: settings.root_path ? T.text : T.dim,
            fontStyle: settings.root_path ? 'normal' : 'italic',
          }}>
            {settings.root_path || 'No workspace configured'}
          </div>
          <button
            onClick={handleBrowse}
            disabled={browsing}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '0 12px',
              background: `${T.cyan}14`,
              border: `1px solid ${T.cyan}33`,
              borderRadius: 4,
              color: T.cyan,
              fontFamily: F,
              fontSize: FS.xxs,
              cursor: browsing ? 'wait' : 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            <FolderOpen size={12} />
            {browsing ? 'Browsing...' : 'Browse'}
          </button>
          {settings.root_path && (
            <button
              onClick={() => updateSettings({ root_path: '' })}
              style={{
                padding: '0 8px',
                background: 'none',
                border: `1px solid ${T.border}`,
                borderRadius: 4,
                color: T.dim,
                fontFamily: F,
                fontSize: FS.xxs,
                cursor: 'pointer',
              }}
            >
              Clear
            </button>
          )}
        </div>
        <span style={descStyle}>
          Blueprint organizes your datasets, models, outputs, and configs in this folder
        </span>
      </div>

      {/* Auto-fill & Watcher toggles */}
      {isConfigured && (
        <>
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>AUTO-FILL PATHS</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button
                onClick={() => updateSettings({ auto_fill_paths: !settings.auto_fill_paths })}
                style={{
                  position: 'relative', width: 36, height: 20, borderRadius: 10,
                  border: 'none', background: settings.auto_fill_paths ? `${T.cyan}40` : T.surface4,
                  cursor: 'pointer', padding: 0, transition: 'background 0.2s',
                }}
              >
                <div style={{
                  position: 'absolute', top: 2, left: settings.auto_fill_paths ? 18 : 2,
                  width: 16, height: 16, borderRadius: '50%',
                  background: settings.auto_fill_paths ? T.cyan : T.dim,
                  transition: 'left 0.2s, background 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
                }} />
              </button>
              <span style={descStyle}>Auto-fill output paths in pipeline blocks</span>
            </div>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>INBOX WATCHER</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button
                onClick={() => updateSettings({ watcher_enabled: !settings.watcher_enabled })}
                style={{
                  position: 'relative', width: 36, height: 20, borderRadius: 10,
                  border: 'none', background: settings.watcher_enabled ? `${T.cyan}40` : T.surface4,
                  cursor: 'pointer', padding: 0, transition: 'background 0.2s',
                }}
              >
                <div style={{
                  position: 'absolute', top: 2, left: settings.watcher_enabled ? 18 : 2,
                  width: 16, height: 16, borderRadius: '50%',
                  background: settings.watcher_enabled ? T.cyan : T.dim,
                  transition: 'left 0.2s, background 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
                }} />
              </button>
              <span style={descStyle}>Auto-categorize files dropped in the inbox folder</span>
            </div>
          </div>

          {/* Status */}
          <div style={{
            padding: 12, background: T.surface3, border: `1px solid ${T.border}`,
            borderRadius: 6,
          }}>
            <div style={{
              fontFamily: F, fontSize: FS.xxs, color: T.dim,
              letterSpacing: '0.1em', fontWeight: 700, marginBottom: 8,
            }}>
              STATUS
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {/* Watcher status */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: status?.watcher_running ? T.green : T.dim,
                  boxShadow: status?.watcher_running ? `0 0 6px ${T.green}80` : 'none',
                }} />
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                  Watcher: {status?.watcher_running ? 'Running' : 'Stopped'}
                </span>
              </div>

              {/* Inbox count */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec }}>
                  Inbox: {status?.inbox_count ?? 0} file{(status?.inbox_count ?? 0) !== 1 ? 's' : ''}
                </span>
              </div>

              {/* Folder health */}
              {status?.folder_health && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                  {Object.entries(status.folder_health).map(([key, exists]) => (
                    <span key={key} style={{
                      fontFamily: F, fontSize: '7px', color: exists ? T.green : T.red,
                      background: exists ? `${T.green}10` : `${T.red}10`,
                      border: `1px solid ${exists ? `${T.green}20` : `${T.red}20`}`,
                      padding: '1px 5px', borderRadius: 3,
                    }}>
                      {exists ? '\u2713' : '\u2717'} {key.replace(/_/g, '/')}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
              <button
                onClick={openInFinder}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '4px 10px', background: 'none',
                  border: `1px solid ${T.border}`, borderRadius: 4,
                  color: T.sec, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
                }}
              >
                <ExternalLink size={10} />
                Open in Finder
              </button>
              <button
                onClick={initialize}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '4px 10px', background: 'none',
                  border: `1px solid ${T.border}`, borderRadius: 4,
                  color: T.sec, fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
                }}
              >
                <RefreshCw size={10} />
                Re-initialize
              </button>
            </div>
          </div>

          {/* Pipeline Config Overrides */}
          <div style={{ marginTop: 16 }}>
            <label style={labelStyle}>PIPELINE CONFIG OVERRIDES</label>
            <button
              onClick={() => setShowWorkspaceConfig(true)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '8px 14px', background: `${T.cyan}10`,
                border: `1px solid ${T.cyan}28`, borderRadius: 6,
                color: T.cyan, fontFamily: F, fontSize: FS.xs, cursor: 'pointer',
              }}
            >
              <Sliders size={12} />
              Manage Workspace Config
            </button>
            <span style={descStyle}>
              Set config overrides applied to all pipelines (e.g. seed, temperature)
            </span>
          </div>

          {showWorkspaceConfig && (
            <WorkspaceConfigPanel onClose={() => setShowWorkspaceConfig(false)} />
          )}
        </>
      )}
    </motion.div>
  )
}

// Lazy-load the WorkspaceConfig panel
function WorkspaceConfigPanel({ onClose }: { onClose: () => void }) {
  const [Component, setComponent] = useState<React.ComponentType<{ onClose: () => void }> | null>(null)
  useEffect(() => {
    import('@/components/Config/WorkspaceConfig').then((mod) => {
      setComponent(() => mod.default)
    })
  }, [])
  if (!Component) return null
  return <Component onClose={onClose} />
}
