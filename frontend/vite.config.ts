import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, "");
  const apiTarget = env.VITE_API_BASE_URL?.trim() || "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    server: {
      host: true,
      port: 5173,
      fs: {
        strict: false,
        allow: [path.resolve(__dirname)],
      },
      proxy: {
        "/api": {
          target: apiTarget.replace(/\/$/, ""),
          changeOrigin: true,
        },
      },
    },
  };
});
