import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

// 开发时 /api 代理到后端 uvicorn（backend.app，默认 8000 端口）。
// apiClient 的 baseUrl 默认是 "/api"，前后端联调无需改代码。
export default defineConfig({
  resolve: {
    alias: {
      // 与 tsconfig.json 的 paths 对齐：@/ → src/
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
