import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    fs: {
      strict: false,
      allow: [path.resolve(__dirname)],
    },
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
