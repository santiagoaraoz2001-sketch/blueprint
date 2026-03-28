/**
 * Registry client — fetches block schemas from the backend API at startup
 * and serves them synchronously to the rest of the frontend.
 *
 * Source of truth is the backend registry API (GET /api/registry/blocks).
 * All API calls use typed responses generated from the OpenAPI schema.
 */

import { api } from '@/api/client'
import type {
  BlockSchema,
  ValidateConnectionResponse,
  RegistryVersionResponse,
} from '@/api/types'
import type { BlockDefinition } from './block-registry-types'

/**
 * The backend BlockSchema is structurally identical to the frontend
 * BlockDefinition — both have the same fields.  We cast through the
 * API boundary so the rest of the frontend can keep using the
 * hand-maintained BlockDefinition type (which includes ConnectorType,
 * ConfigField, etc.) without coupling to the generated OpenAPI types.
 */
function toBlockDefinition(dto: BlockSchema): BlockDefinition {
  // The shapes are identical; this is a type-level bridge only.
  return dto as unknown as BlockDefinition
}

export class RegistryClient {
  private blocks: Map<string, BlockDefinition> = new Map()
  private _version = 0
  private _initialized = false
  private _initPromise: Promise<void> | null = null

  /** Whether the registry has been loaded from the backend. */
  get initialized(): boolean {
    return this._initialized
  }

  /**
   * Fetch all block schemas from the backend and populate the local map.
   * Safe to call multiple times — subsequent calls return the same promise.
   */
  async initialize(): Promise<void> {
    if (this._initialized) return
    if (this._initPromise) return this._initPromise

    this._initPromise = this._doInit()
    return this._initPromise
  }

  private async _doInit(): Promise<void> {
    const [dtos, versionRes] = await Promise.all([
      api.get<BlockSchema[]>('/registry/blocks'),
      api.get<RegistryVersionResponse>('/registry/version'),
    ])

    this.blocks.clear()
    for (const dto of dtos) {
      const def = toBlockDefinition(dto)
      this.blocks.set(def.type, def)
    }
    this._version = versionRes.version
    this._initialized = true

    // Also merge custom blocks from localStorage (backward compat)
    this._mergeCustomBlocks()
  }

  /** Merge custom blocks from localStorage into the registry map. */
  private _mergeCustomBlocks(): void {
    try {
      const raw = localStorage.getItem('blueprint-custom-blocks')
      if (raw) {
        const customs: BlockDefinition[] = JSON.parse(raw)
        for (const custom of customs) {
          // Custom blocks don't override builtins
          if (!this.blocks.has(custom.type)) {
            this.blocks.set(custom.type, custom)
          }
        }
      }
    } catch { /* ignore parse errors */ }
  }

  /** Look up a single block by type.  O(1) Map lookup. */
  getBlock(type: string): BlockDefinition | undefined {
    return this.blocks.get(type)
  }

  /** List blocks filtered by category. */
  listByCategory(cat: string): BlockDefinition[] {
    const result: BlockDefinition[] = []
    for (const block of this.blocks.values()) {
      if (block.category === cat) result.push(block)
    }
    return result
  }

  /** Return all blocks as an array. */
  listAll(): BlockDefinition[] {
    return Array.from(this.blocks.values())
  }

  /** Group blocks by category (same shape as old getBlocksByCategory). */
  getBlocksByCategory(): Record<string, BlockDefinition[]> {
    const groups: Record<string, BlockDefinition[]> = {}
    for (const block of this.blocks.values()) {
      if (!groups[block.category]) groups[block.category] = []
      groups[block.category].push(block)
    }
    return groups
  }

  /** Validate a connection via the backend API (typed response). */
  async validateConnection(
    srcType: string,
    srcPort: string,
    dstType: string,
    dstPort: string,
  ): Promise<ValidateConnectionResponse> {
    return api.post<ValidateConnectionResponse>(
      '/registry/validate-connection',
      { src_type: srcType, src_port: srcPort, dst_type: dstType, dst_port: dstPort },
    )
  }

  /** Trigger a backend re-scan. Returns new version. */
  async refresh(): Promise<number> {
    const res = await api.post<RegistryVersionResponse>('/registry/refresh')
    // Re-initialize with fresh data
    this._initialized = false
    this._initPromise = null
    await this.initialize()
    return res.version
  }

  /** Current registry version. */
  getVersion(): number {
    return this._version
  }
}

/** Singleton registry client used across the app. */
export const registry = new RegistryClient()

// ─── Drop-in replacements for old block-registry.ts functions ────────
// These delegate to the singleton so existing call sites can be updated
// with minimal diff.

export function getBlockDefinition(type: string): BlockDefinition | undefined {
  return registry.getBlock(type)
}

export function getBlocksByCategory(): Record<string, BlockDefinition[]> {
  return registry.getBlocksByCategory()
}

/**
 * Return all blocks as an array.
 * Drop-in replacement for the old `BLOCK_REGISTRY` constant.
 */
export function getAllBlocks(): BlockDefinition[] {
  return registry.listAll()
}
