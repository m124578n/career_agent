/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 正式環境的後端 API base，如 https://xxx.zeabur.app/api。dev 留空走 Vite proxy /api */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
