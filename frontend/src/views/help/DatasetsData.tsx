import { T, F, FS } from '@/lib/design-tokens'
import SectionAnchor from '@/components/Help/SectionAnchor'
import { Database, Search, FileSpreadsheet, ArrowRightLeft } from 'lucide-react'
import { helpCard as card, helpBody as body, helpTip as tip, helpStepList as stepList, helpCode as code, helpCodeBlock as codeBlock } from './styles'

export const DATASETS_DATA_TEXT = `Datasets & Data Management. Blueprint provides a complete dataset management system for importing, previewing, scanning, and transforming data files. HuggingFace Import: Use the Blueprint Chrome extension to import datasets directly from HuggingFace dataset pages with one click. The extension sends the dataset config to your local Blueprint instance. Dataset Builder: The dataset_builder block prepares training-ready datasets from raw data with splitting, shuffling, and format conversion. Supported Formats: CSV, TSV, JSON, JSONL, Parquet, SQLite, Excel (xlsx/xls), YAML, and plain text files (txt, md, log). Registering Datasets: In the Datasets view, click "+ Add Dataset" to register a file from your filesystem. Provide a name, source path, and optional description and tags. The dataset is registered in Blueprint's database with metadata like row count, column count, and file size. Dataset Preview: Click any dataset to see a paginated preview of its contents. The preview supports all formats — CSV shows as a table, JSON/JSONL shows flattened rows, SQLite reads the first table, and even Parquet files are previewed (requires pyarrow). You can adjust the number of preview rows (1-500) and offset for pagination. File Scanner: Use the file scanner (POST /api/datasets/scan/discover) to automatically discover data files across your filesystem. By default it scans Desktop, Documents, Downloads, Data, and Projects folders. You can specify custom directories, filter by extension, set size limits, and control scan depth (max 6 levels). Results are sorted by modification time (newest first). Batch Registration: After scanning, select discovered files and register them in bulk via the batch registration endpoint. Already-registered files are skipped automatically. Dataset Snapshots: Create point-in-time snapshots of any dataset for versioning. Snapshots are stored in ~/.specific-labs/snapshots/{dataset_id}/ and automatically cleaned up after 24 hours. Restore any snapshot to revert the dataset to a previous state. Re-Architecture Templates: Transform datasets between formats using built-in templates. Standard Tabular — flattens nested JSON/YAML into CSV with consistent columns. ML Train/Test Split — splits any dataset into 80/20 train/test CSV files with deterministic shuffle (seed=42). JSONL Normalize — converts any structured data into one-JSON-object-per-line format. Chat/Instruct Format — converts tabular data with input/output columns into chat-style JSONL for LLM fine-tuning, auto-detecting common column names (input, question, prompt → user; output, answer, response → assistant). Templates run in isolated subprocesses with 120-second timeout for safety.`

export default function DatasetsData() {
  return (
    <div>
      <SectionAnchor id="datasets-data" title="Datasets & Data" level={1}>
        <Database size={22} color={T.cyan} />
      </SectionAnchor>

      {/* HuggingFace Import */}
      <div style={card}>
        <p style={body}>
          <strong>HuggingFace Import:</strong> Use the Blueprint Chrome extension to import datasets
          directly from HuggingFace dataset pages. Browse any dataset on huggingface.co, click the
          Blueprint extension icon, and the dataset is sent to your local Blueprint instance.
        </p>
        <ul style={stepList}>
          <li>Install the Chrome extension from <span style={code}>extensions/chrome-blueprint-hf/</span></li>
          <li>Navigate to any HuggingFace dataset page</li>
          <li>Click the Blueprint extension icon to import</li>
          <li>The dataset appears in your local Datasets view</li>
        </ul>
        <p style={{ ...body, marginTop: 12 }}>
          <strong>Dataset Builder:</strong> The <span style={code}>dataset_builder</span> block
          prepares training-ready datasets from raw data with splitting, shuffling, and format conversion.
          Find it under the Data category in the block library.
        </p>
      </div>

      {/* Supported Formats */}
      <SectionAnchor id="datasets-data/formats" title="Supported Formats" level={2} />
      <div style={card}>
        <p style={body}>
          Blueprint supports a wide range of data formats for import, preview, and transformation:
        </p>
        <ul style={stepList}>
          <li><span style={code}>.csv</span> / <span style={code}>.tsv</span> — Delimited tabular data with auto-dialect detection</li>
          <li><span style={code}>.json</span> — JSON arrays, objects, or columnar format</li>
          <li><span style={code}>.jsonl</span> — One JSON object per line (streaming-friendly)</li>
          <li><span style={code}>.parquet</span> — Apache Parquet columnar storage (requires pyarrow)</li>
          <li><span style={code}>.db</span> / <span style={code}>.sqlite</span> / <span style={code}>.sqlite3</span> — SQLite databases (reads first table)</li>
          <li><span style={code}>.xlsx</span> / <span style={code}>.xls</span> — Excel spreadsheets (requires openpyxl)</li>
          <li><span style={code}>.yaml</span> / <span style={code}>.yml</span> — YAML data files</li>
          <li><span style={code}>.txt</span> / <span style={code}>.md</span> / <span style={code}>.log</span> — Plain text (line-by-line)</li>
        </ul>
      </div>

      {/* Registering & Preview */}
      <SectionAnchor id="datasets-data/preview" title="Registering & Preview" level={2} />
      <div style={card}>
        <p style={body}>
          Register datasets by providing a name and file path. Once registered, click any dataset
          to see a paginated preview of its contents rendered as a table.
        </p>
        <ul style={stepList}>
          <li>Navigate to the <strong>Datasets</strong> view from the sidebar</li>
          <li>Click <strong>+ Add Dataset</strong> and fill in name, path, and optional tags</li>
          <li>Click a dataset row to open the preview panel</li>
          <li>Adjust rows per page (1–500) and offset for pagination</li>
        </ul>
        <div style={tip}>
          The first preview also caches metadata (row count, column count, columns) so subsequent
          loads are faster.
        </div>
      </div>

      {/* File Scanner */}
      <SectionAnchor id="datasets-data/scanner" title="File Scanner" level={2} />
      <div style={card}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <Search size={14} color={T.cyan} />
          <span style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text }}>
            Automatic File Discovery
          </span>
        </div>
        <p style={body}>
          The file scanner automatically discovers data-compatible files across your filesystem.
          By default it scans Desktop, Documents, Downloads, Data, and Projects folders under
          your home directory.
        </p>
        <div style={codeBlock}>
{`POST /api/datasets/scan/discover
{
  "directories": ["/path/to/scan"],
  "extensions": [".csv", ".json", ".parquet"],
  "max_results": 500,
  "max_depth": 6,
  "min_size_bytes": 0,
  "max_size_bytes": 0
}`}
        </div>
        <p style={body}>
          Directories like <span style={code}>.git</span>, <span style={code}>node_modules</span>,
          and <span style={code}>__pycache__</span> are automatically skipped. Results include
          file path, name, size, modification time, and parent directory.
        </p>
        <div style={tip}>
          After scanning, use <strong>Batch Registration</strong> to register multiple
          files at once. Already-registered files are automatically skipped.
        </div>
      </div>

      {/* Snapshots */}
      <SectionAnchor id="datasets-data/snapshots" title="Snapshots & Versioning" level={2} />
      <div style={card}>
        <p style={body}>
          Create point-in-time snapshots of any dataset for simple versioning. Snapshots are
          stored alongside your data and automatically cleaned up after 24 hours.
        </p>
        <ul style={stepList}>
          <li><strong>Create:</strong> POST <span style={code}>/api/datasets/&#123;id&#125;/snapshots</span> — copies the current file</li>
          <li><strong>List:</strong> GET <span style={code}>/api/datasets/&#123;id&#125;/snapshots</span> — shows available snapshots with sizes</li>
          <li><strong>Restore:</strong> POST <span style={code}>/api/datasets/&#123;id&#125;/snapshots/&#123;snap_id&#125;/restore</span> — overwrites current file, bumps version</li>
        </ul>
      </div>

      {/* Re-Architecture Templates */}
      <SectionAnchor id="datasets-data/templates" title="Re-Architecture Templates" level={2} />
      <div style={card}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <ArrowRightLeft size={14} color={T.cyan} />
          <span style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text }}>
            Transform Data Structure
          </span>
        </div>
        <p style={body}>
          Apply built-in templates to transform datasets between formats. Templates run in
          isolated subprocesses with a 120-second timeout for safety.
        </p>
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column' as const, gap: 8 }}>
          {[
            {
              name: 'Standard Tabular',
              desc: 'Flatten nested JSON/YAML into a CSV with consistent columns',
              out: '.csv',
            },
            {
              name: 'ML Train/Test Split',
              desc: 'Split into 80/20 train/test CSV files (seed=42)',
              out: '.csv',
            },
            {
              name: 'JSONL Normalize',
              desc: 'Convert any structured data into one-JSON-per-line format',
              out: '.jsonl',
            },
            {
              name: 'Chat/Instruct Format',
              desc: 'Convert tabular input/output columns to chat-style JSONL for LLM fine-tuning',
              out: '.jsonl',
            },
          ].map((t) => (
            <div
              key={t.name}
              style={{
                padding: '8px 12px',
                background: T.surface1,
                border: `1px solid ${T.border}`,
                display: 'flex',
                alignItems: 'center',
                gap: 10,
              }}
            >
              <FileSpreadsheet size={12} color={T.cyan} />
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 600 }}>
                  {t.name}
                </div>
                <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>
                  {t.desc}
                </div>
              </div>
              <span style={code}>{t.out}</span>
            </div>
          ))}
        </div>
        <div style={tip}>
          The Chat/Instruct template auto-detects common column names: "input", "question",
          "prompt" → user role; "output", "answer", "response" → assistant role.
        </div>
      </div>
    </div>
  )
}
