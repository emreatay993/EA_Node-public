import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const hostRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(hostRoot, "..", "..");
const packagedAssetRoot = path.resolve(
  repoRoot,
  "ea_node_editor",
  "web_assets",
  "excalidraw_host",
);

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    outDir: packagedAssetRoot,
    emptyOutDir: true,
    sourcemap: false,
    assetsDir: "",
    cssCodeSplit: true,
    rollupOptions: {
      output: {
        entryFileNames: "[name]-[hash].js",
        chunkFileNames: "[name]-[hash].js",
        assetFileNames: "[name]-[hash][extname]",
      },
    },
  },
});
