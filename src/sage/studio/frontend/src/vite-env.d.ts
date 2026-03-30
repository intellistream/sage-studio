/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_BACKEND_BASE_URL?: string
  readonly VITE_BACKEND_PORT?: string
  readonly VITE_LLM_BASE_URL?: string
  // 更多环境变量可以在这里添加
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
