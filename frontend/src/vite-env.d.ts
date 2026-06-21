/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 正式環境的後端 API base，如 https://xxx.zeabur.app/api。dev 留空走 Vite proxy /api */
  readonly VITE_API_BASE_URL?: string;
  /** Google OAuth Client ID。未設 → 停用登入（本機開發） */
  readonly VITE_GOOGLE_CLIENT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
