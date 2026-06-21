import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 把 /api 轉到 FastAPI 後端，前端 fetch 走相對路徑即可
      "/api": "http://localhost:8000",
    },
  },
});
