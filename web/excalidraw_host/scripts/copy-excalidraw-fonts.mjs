import { cp, rm, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const hostRoot = path.resolve(scriptRoot, "..");
const repoRoot = path.resolve(hostRoot, "..", "..");
const assetRoot = path.resolve(
  repoRoot,
  "ea_node_editor",
  "web_assets",
  "excalidraw_host",
);
const sourceFontRoot = path.resolve(
  hostRoot,
  "node_modules",
  "@excalidraw",
  "excalidraw",
  "dist",
  "prod",
  "fonts",
);
const targetFontRoot = path.join(assetRoot, "fonts");

async function assertDirectory(candidate, label) {
  const entry = await stat(candidate).catch(() => null);
  if (!entry?.isDirectory()) {
    throw new Error(`${label} directory was not found: ${candidate}`);
  }
}

async function assertFile(candidate, label) {
  const entry = await stat(candidate).catch(() => null);
  if (!entry?.isFile()) {
    throw new Error(`${label} file was not found: ${candidate}`);
  }
}

await assertDirectory(assetRoot, "Excalidraw host bundle");
await assertDirectory(sourceFontRoot, "Excalidraw font source");

await rm(targetFontRoot, { recursive: true, force: true });
await cp(sourceFontRoot, targetFontRoot, { recursive: true });

await assertFile(
  path.join(targetFontRoot, "Virgil", "Virgil-Regular.woff2"),
  "Excalidraw Virgil font",
);
await assertFile(
  path.join(targetFontRoot, "Cascadia", "CascadiaCode-Regular.woff2"),
  "Excalidraw Cascadia font",
);

console.log("Copied Excalidraw runtime fonts into the packaged host bundle.");
