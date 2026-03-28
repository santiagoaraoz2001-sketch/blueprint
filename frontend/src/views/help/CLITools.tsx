import { T } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import { Terminal } from 'lucide-react'
import { helpCard as card, helpBody as body, helpStepList as stepList, helpCodeBlock as codeBlock } from './styles'

export const CLI_TOOLS_TEXT = `CLI Tools. Block Test Runner: python -m backend.tests.block_runner <block_dir> [options]. Options: --fixture small|medium|realistic, --config key=value, --verbose, --timeout SECONDS. Block Scaffold: python scripts/scaffold_block.py --name "Name" --category data --type my_block. Creates skeleton block.yaml + run.py. Block Registry Codegen: python scripts/generate_block_registry.py. Regenerates generated TypeScript types and config interfaces from all block.yaml files. Also regenerates port compatibility code from docs/PORT_COMPATIBILITY.yaml. Run after adding or modifying blocks. The backend registry API (GET /api/registry/blocks) is the primary source of truth at runtime. Plugin Manager: python scripts/blueprint_plugin.py [list|install|remove|create|info] [args]. Launch Script: ./launch.sh. One-command launcher: creates venv, installs deps, starts backend + frontend. Pipeline Validator API: POST /api/pipelines/{id}/validate. Also accessible via the Validate button in the Pipeline Editor toolbar.`

export default function CLITools() {
  return (
    <div>
      <SectionAnchor id="cli-tools" title="CLI Tools" level={1}>
        <Terminal size={22} color={T.cyan} />
      </SectionAnchor>

      {/* 10.1 Block Test Runner */}
      <SectionAnchor id="cli-tools/test-runner" title="Block Test Runner" level={2} />
      <div style={card}>
        <div style={codeBlock}>
          python -m backend.tests.block_runner &lt;block_dir&gt; [options]
        </div>
        <p style={body}>Options:</p>
        <ul style={stepList}>
          <li>
            <strong>--fixture</strong> small | medium | realistic
          </li>
          <li>
            <strong>--config</strong> key=value (override config fields)
          </li>
          <li>
            <strong>--verbose</strong> (detailed output)
          </li>
          <li>
            <strong>--timeout</strong> SECONDS
          </li>
        </ul>
      </div>

      {/* 10.2 Block Scaffold */}
      <SectionAnchor id="cli-tools/scaffold" title="Block Scaffold" level={2} />
      <div style={card}>
        <div style={codeBlock}>
          python scripts/scaffold_block.py --name &quot;Name&quot; --category data --type my_block
        </div>
        <p style={body}>
          Creates a skeleton <code>block.yaml</code> + <code>run.py</code> in{' '}
          <code>blocks/data/my_block/</code>.
        </p>
      </div>

      {/* 10.3 Block Registry Codegen */}
      <SectionAnchor id="cli-tools/codegen" title="Block Registry Codegen" level={2} />
      <div style={card}>
        <div style={codeBlock}>python scripts/generate_block_registry.py</div>
        <p style={body}>
          Regenerates TypeScript config interfaces and block-type unions from all{' '}
          <code>block.yaml</code> files. Run this after adding or modifying any block.
          At runtime, the backend registry API (<code>/api/registry/blocks</code>) is the
          source of truth.
        </p>
      </div>

      {/* 10.4 Plugin Manager */}
      <SectionAnchor id="cli-tools/plugin-manager" title="Plugin Manager" level={2} />
      <div style={card}>
        <div style={codeBlock}>
          python scripts/blueprint_plugin.py [list|install|remove|create|info] [args]
        </div>
        <p style={body}>
          Manage plugins from the command line. See the Plugin System section for detailed usage.
        </p>
      </div>

      {/* 10.5 Launch Script */}
      <SectionAnchor id="cli-tools/launch" title="Launch Script" level={2} />
      <div style={card}>
        <div style={codeBlock}>./launch.sh</div>
        <p style={body}>
          One-command launcher: creates Python venv, installs dependencies, starts the backend
          server and frontend dev server.
        </p>
      </div>

      {/* 10.6 Pipeline Validator API */}
      <SectionAnchor id="cli-tools/validator-api" title="Pipeline Validator (API)" level={2} />
      <div style={card}>
        <div style={codeBlock}>
          POST /api/pipelines/&#123;id&#125;/validate
        </div>
        <p style={body}>
          Also accessible via the Validate button (shield icon) in the Pipeline Editor toolbar or{' '}
          <code>Cmd+Shift+V</code>.
        </p>
      </div>
    </div>
  )
}
