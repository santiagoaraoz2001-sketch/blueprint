/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_PORT?: string
  readonly VITE_API_TARGET?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

// Global constants injected by Vite define
declare const __APP_VERSION__: string
