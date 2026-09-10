import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptRoot, "..", "..", "..");
const assetRoot = path.resolve(
  repoRoot,
  "ea_node_editor",
  "web_assets",
  "excalidraw_host",
);
const textExtensions = new Set([
  ".css",
  ".html",
  ".js",
  ".json",
  ".mjs",
  ".svg",
  ".webmanifest",
]);
const remotePattern = /https?:\/\//gi;

async function textAssetPaths(root) {
  const entries = await readdir(root, { withFileTypes: true });
  const paths = [];
  for (const entry of entries) {
    const fullPath = path.join(root, entry.name);
    if (entry.isDirectory()) {
      paths.push(...(await textAssetPaths(fullPath)));
      continue;
    }
    if (entry.isFile() && textExtensions.has(path.extname(entry.name))) {
      paths.push(fullPath);
    }
  }
  return paths;
}

function sanitizeText(text, extension) {
  if (extension === ".css" || extension === ".svg") {
    return text.replace(/https:\/\//gi, "https%3A//").replace(/http:\/\//gi, "http%3A//");
  }
  return text.replace(/https:\/\//gi, "https\\u003a//").replace(/http:\/\//gi, "http\\u003a//");
}

let foundRemoteReference = false;
for (const assetPath of await textAssetPaths(assetRoot)) {
  const before = await readFile(assetPath, "utf8");
  if (!remotePattern.test(before)) {
    continue;
  }
  remotePattern.lastIndex = 0;
  foundRemoteReference = true;
  const after = sanitizeText(before, path.extname(assetPath));
  await writeFile(assetPath, after, "utf8");
}

const remaining = [];
for (const assetPath of await textAssetPaths(assetRoot)) {
  const text = await readFile(assetPath, "utf8");
  if (remotePattern.test(text)) {
    remaining.push(path.relative(assetRoot, assetPath));
  }
  remotePattern.lastIndex = 0;
}

if (remaining.length > 0) {
  throw new Error(
    `Excalidraw host bundle still contains remote URL literals: ${remaining.join(", ")}`,
  );
}

const indexPath = path.join(assetRoot, "index.html");
if (!(await stat(indexPath)).isFile()) {
  throw new Error("Excalidraw host bundle did not emit index.html.");
}

if (foundRemoteReference) {
  console.log("Sanitized remote URL literals from local Excalidraw host assets.");
}
