import { T, F, FS } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import { Settings, Palette, Brain, ToggleLeft, Flag, FolderOpen } from 'lucide-react'
import { helpCard as card, helpBody as body, helpTip as tip, helpStepList as stepList, helpCode as code } from './styles'

export const SETTINGS_CONFIG_TEXT = `Settings and Configuration. Appearance: Theme Dark/Light with live preview cards. Code font: 4 options. Font size: Compact, Default, Comfortable, Large. LLM Providers: Ollama (default, local) at http://localhost:11434. MLX (Apple Silicon) at http://localhost:8080. OpenAI and Anthropic require API key (stored locally). Manual: custom endpoint URL. UI Mode: Simple vs Professional toggle. See Getting Started section. Feature Flags: GET /api/system/features returns enabled optional features. Environment variables: BLUEPRINT_ENABLE_MARKETPLACE, BLUEPRINT_HEARTBEAT_TIMEOUT, BLUEPRINT_RECOVERY_INTERVAL. Data Location: All data in ~/.specific-labs/. Database: specific.db (SQLite, WAL mode). Artifacts: artifacts/{run_id}/. Plugins: plugins/. Custom blocks: custom_blocks/. Logs: logs/blueprint.jsonl.`

export default function SettingsConfig() {
  return (
    <div>
      <SectionAnchor id="settings-config" title="Settings & Configuration" level={1}>
        <Settings size={22} color={T.accent} />
      </SectionAnchor>

      {/* 11.1 Appearance */}
      <SectionAnchor id="settings-config/appearance" title="Appearance" level={2}>
        <Palette size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <ul style={stepList}>
          <li>
            <strong>Theme:</strong> Dark / Light with live preview cards
          </li>
          <li>
            <strong>Code font:</strong> 4 options (JetBrains Mono, Inter, Fira Code, IBM Plex Mono)
          </li>
          <li>
            <strong>Font size:</strong> Compact / Default / Comfortable / Large
          </li>
          <li>
            <strong>Accent color:</strong> Cyan, Orange, Green, Blue, Purple, Pink
          </li>
        </ul>
      </div>

      {/* 11.2 LLM Providers */}
      <SectionAnchor id="settings-config/llm-providers" title="LLM Providers" level={2}>
        <Brain size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <ul style={stepList}>
          <li>
            <strong>Ollama</strong> (default, local):{' '}
            <span style={code}>http://localhost:11434</span>
          </li>
          <li>
            <strong>MLX</strong> (Apple Silicon):{' '}
            <span style={code}>http://localhost:8080</span>
          </li>
          <li>
            <strong>OpenAI, Anthropic:</strong> API key required (stored locally, never transmitted)
          </li>
          <li>
            <strong>Manual:</strong> Custom endpoint URL for any OpenAI-compatible server
          </li>
        </ul>
        <div style={tip}>
          API keys are stored locally in your settings file and never leave your machine.
        </div>
      </div>

      {/* 11.3 UI Mode */}
      <SectionAnchor id="settings-config/ui-mode" title="UI Mode" level={2}>
        <ToggleLeft size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          Simple vs Professional toggle. See the{' '}
          <strong>Getting Started → Simple vs Professional Mode</strong> section for details on what
          each mode shows and hides.
        </p>
      </div>

      {/* 11.4 Feature Flags */}
      <SectionAnchor id="settings-config/feature-flags" title="Feature Flags" level={2}>
        <Flag size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <ul style={stepList}>
          <li>
            <span style={code}>GET /api/system/features</span> — Returns enabled optional features
          </li>
          <li>
            Environment variables:
            <ul style={{ paddingLeft: 16, marginTop: 4 }}>
              <li>
                <span style={code}>BLUEPRINT_ENABLE_MARKETPLACE</span> — Enable/disable the
                marketplace
              </li>
              <li>
                <span style={code}>BLUEPRINT_HEARTBEAT_TIMEOUT</span> — Stale run detection
                threshold
              </li>
              <li>
                <span style={code}>BLUEPRINT_RECOVERY_INTERVAL</span> — Auto-recovery check
                interval
              </li>
            </ul>
          </li>
        </ul>
      </div>

      {/* 11.5 Data Location */}
      <SectionAnchor id="settings-config/data-location" title="Data Location" level={2}>
        <FolderOpen size={17} color={T.accent} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          All data is stored in <span style={code}>~/.specific-labs/</span>:
        </p>
        <ul style={stepList}>
          <li>
            <span style={code}>specific.db</span> — SQLite database (WAL mode)
          </li>
          <li>
            <span style={code}>artifacts/&#123;run_id&#125;/</span> — Run artifacts
          </li>
          <li>
            <span style={code}>plugins/</span> — Installed plugins
          </li>
          <li>
            <span style={code}>custom_blocks/</span> — User-created blocks
          </li>
          <li>
            <span style={code}>logs/blueprint.jsonl</span> — Structured logs
          </li>
        </ul>
      </div>
    </div>
  )
}
