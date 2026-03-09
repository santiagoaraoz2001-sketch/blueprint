import { useState } from 'react'
import { motion } from 'framer-motion'
import { T, F, FD, FS, getTheme } from '@/lib/design-tokens'
import { playSound } from '@/lib/audio'
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
/*  SettingsView                                                       */
/* ------------------------------------------------------------------ */

export default function SettingsView() {
  const {
    theme, accentColor, font, fontSize, demoMode, autoSaveInterval,
    setTheme, setAccentColor, setFont, setFontSize, setDemoMode, setAutoSaveInterval,
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
              </div>
            </div>

            {/* Accent Color selector */}
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>ACCENT COLOR</label>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                {ACCENT_COLORS.map((color) => {
                  const active = accentColor === color.id
                  const hex = (getTheme(theme) as any)[color.token]
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
                  v0.1.0
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
