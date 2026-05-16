/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute backend API base, e.g. http://localhost:8000/api (dev) or
   *  https://api.<domain>/api (prod). Cross-origin → backend needs CORS. */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
