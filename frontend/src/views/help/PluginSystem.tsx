import { T, FS } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import { Puzzle, Download, Shield, Settings, Wrench, BarChart3 } from 'lucide-react'
import { helpCard as card, helpBody as body, helpTip as tip, helpStepList as stepList, helpCode as code } from './styles'

export const PLUGIN_SYSTEM_TEXT = `Plugin System. Plugins extend Blueprint with new blocks, export connectors, and Monitor panels. Plugins live in ~/.specific-labs/plugins/. Installing Plugins: CLI python scripts/blueprint_plugin.py install <source> (git URL or local path). Each plugin has plugin.yaml manifest: name, version, author, type, permissions, dependencies. After installing, restart Blueprint or Settings → Plugins → Reload. Plugin Permissions: Plugins declare permissions: network, filesystem:read, filesystem:write, gpu, secrets. Blueprint shows permission dialog on first enable. Managing Plugins: list, remove, create, info commands via blueprint_plugin.py. API: GET /api/plugins/ lists all, POST /api/plugins/{name}/enable|disable toggles. Creating Plugins: Plugin structure: plugin.yaml, __init__.py with register() function, optional blocks/ directory, README.md. The register(registry) function is called on load. W&B Monitor Plugin (Reference): Located at examples/plugins/wandb-monitor/. Provides wandb_logger block for streaming metrics to W&B in real-time.`

export default function PluginSystem() {
  return (
    <div>
      <SectionAnchor id="plugin-system" title="Plugin System" level={1}>
        <Puzzle size={22} color={T.cyan} />
      </SectionAnchor>

      {/* 8.1 Overview */}
      <SectionAnchor id="plugin-system/overview" title="Overview" level={2}>
        <Puzzle size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          Plugins extend Blueprint with new blocks, export connectors, and Monitor panels. Plugins
          live in <span style={code}>~/.specific-labs/plugins/</span>.
        </p>
      </div>

      {/* 8.2 Installing Plugins */}
      <SectionAnchor id="plugin-system/installing" title="Installing Plugins" level={2}>
        <Download size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          <strong>How:</strong>
        </p>
        <ul style={stepList}>
          <li>
            CLI: <span style={code}>python scripts/blueprint_plugin.py install &lt;source&gt;</span>{' '}
            (git URL or local path)
          </li>
          <li>
            Each plugin has a <span style={code}>plugin.yaml</span> manifest declaring: name,
            version, author, type, permissions, dependencies
          </li>
          <li>After installing, restart Blueprint or go to Settings → Plugins → &ldquo;Reload&rdquo;</li>
        </ul>
      </div>

      {/* 8.3 Plugin Permissions */}
      <SectionAnchor id="plugin-system/permissions" title="Plugin Permissions" level={2}>
        <Shield size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>
          Plugins declare the permissions they need in <span style={code}>plugin.yaml</span>:
        </p>
        <ul style={stepList}>
          <li>
            <span style={code}>network</span> — Internet access
          </li>
          <li>
            <span style={code}>filesystem:read</span> — Read local files
          </li>
          <li>
            <span style={code}>filesystem:write</span> — Write local files
          </li>
          <li>
            <span style={code}>gpu</span> — GPU access
          </li>
          <li>
            <span style={code}>secrets</span> — Access to API keys
          </li>
        </ul>
        <p style={{ ...body, marginTop: 8 }}>
          Blueprint shows a permission dialog on first enable: &ldquo;Plugin &apos;X&apos; requests: Network
          access, Secret key access. Allow?&rdquo; Plugins without declared permissions cannot access
          restricted resources.
        </p>
      </div>

      {/* 8.4 Managing Plugins */}
      <SectionAnchor id="plugin-system/managing" title="Managing Plugins" level={2}>
        <Settings size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <ul style={stepList}>
          <li>
            <span style={code}>python scripts/blueprint_plugin.py list</span> — Show installed
            plugins
          </li>
          <li>
            <span style={code}>python scripts/blueprint_plugin.py remove &lt;name&gt;</span> —
            Uninstall
          </li>
          <li>
            <span style={code}>python scripts/blueprint_plugin.py create &lt;name&gt; --type connector</span>{' '}
            — Scaffold a new plugin
          </li>
          <li>
            <span style={code}>python scripts/blueprint_plugin.py info &lt;name&gt;</span> — Show
            details
          </li>
        </ul>
        <p style={{ ...body, marginTop: 8 }}>
          <strong>API:</strong>{' '}
          <span style={code}>GET /api/plugins/</span> lists all plugins with status.{' '}
          <span style={code}>POST /api/plugins/&#123;name&#125;/enable|disable</span> toggles a
          plugin.
        </p>
      </div>

      {/* 8.5 Creating Plugins */}
      <SectionAnchor id="plugin-system/creating" title="Creating Plugins" level={2}>
        <Wrench size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <p style={body}>Plugin structure:</p>
        <div
          style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: FS.xs,
            color: T.sec,
            background: T.surface1,
            padding: 14,
            lineHeight: 1.8,
            marginTop: 8,
            whiteSpace: 'pre',
          }}
        >
          {`~/.specific-labs/plugins/my-plugin/
  plugin.yaml       # Manifest
  __init__.py        # Entry point with register() function
  blocks/            # Optional: additional blocks
  README.md          # Documentation`}
        </div>
        <p style={{ ...body, marginTop: 12 }}>
          The <span style={code}>register(registry)</span> function is called on load. Use it to
          register panels, connectors, or log initialization.
        </p>
      </div>

      {/* 8.6 W&B Monitor Plugin */}
      <SectionAnchor id="plugin-system/wandb-plugin" title="W&B Monitor Plugin (Reference)" level={2}>
        <BarChart3 size={17} color={T.cyan} />
      </SectionAnchor>
      <div style={card}>
        <ul style={stepList}>
          <li>
            Located at <span style={code}>examples/plugins/wandb-monitor/</span> in the repo
          </li>
          <li>
            Provides a <span style={code}>wandb_logger</span> block that initializes a W&B run
            during pipeline execution
          </li>
          <li>
            Place it in your pipeline before training blocks to stream metrics to W&B in real-time
          </li>
          <li>Config: API key, project, entity, run name, log system metrics toggle</li>
        </ul>
        <div style={tip}>
          The W&B Monitor Plugin is the best reference for building your own plugins. Study its
          plugin.yaml and register() function.
        </div>
      </div>
    </div>
  )
}
