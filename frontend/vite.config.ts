import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// react-draggable@4.7.0 leaves this Node-style debug flag in its ESM build.
// Fold it out in both normal transforms and Vite's development dependency bundle.
const draggableDebugDefine = {
  "process.env.DRAGGABLE_DEBUG": "false"
};

export default defineConfig({
  define: draggableDebugDefine,
  plugins: [react()],
  optimizeDeps: {
    esbuildOptions: {
      define: draggableDebugDefine
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          charts: ["recharts"],
          grid: ["react-grid-layout"]
        }
      }
    }
  },
  test: {
    environment: "jsdom",
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
    globals: true,
    setupFiles: "./src/test/setup.ts"
  }
});
