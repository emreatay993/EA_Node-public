import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Excalidraw,
  exportToBlob,
  serializeAsJSON,
} from "@excalidraw/excalidraw";
import "@excalidraw/excalidraw/index.css";
import "./styles.css";
import { SnapshotController, type SnapshotResult } from "./snapshot-controller";

type JsonObject = Record<string, unknown>;
type SceneState = {
  type: "excalidraw";
  elements: unknown[];
  appState: JsonObject;
  files: JsonObject;
};

type BridgeObject = {
  load_state?: (callback: (value: unknown) => void) => unknown;
  save_scene?: (payload: unknown, callback?: (value: unknown) => void) => unknown;
  note_revision?: (revision: number) => void;
  snapshot_status?: (payload: unknown) => void;
  finish_close?: (payload: unknown, callback?: (value: unknown) => void) => unknown;
  finish_without_preview?: (payload: unknown, callback?: (value: unknown) => void) => unknown;
  start_editor?: (callback?: (value: unknown) => void) => unknown;
  asset_request?: (assetId: string, callback?: (value: unknown) => void) => unknown;
  commit_snapshot?: (payload?: unknown, callback?: (value: unknown) => void) => unknown;
  scene_state?: unknown;
  last_error?: string;
};

type QWebChannelInstance = {
  objects?: Record<string, BridgeObject>;
};

type QWebChannelConstructor = new (
  transport: unknown,
  callback: (channel: QWebChannelInstance) => void,
) => unknown;

type ExcalidrawApi = {
  refresh?: () => void;
  scrollToContent?: (target?: unknown, opts?: JsonObject) => void;
};

type HostApi = {
  bridgeReady: () => boolean;
  flushSave: () => Promise<boolean>;
  getSceneState: () => SceneState;
  requestClose: () => void;
  retryPreview: () => void;
  closeWithoutPreview: () => void;
  reloadEditor: () => void;
};

declare global {
  interface Window {
    qt?: { webChannelTransport?: unknown };
    QWebChannel?: QWebChannelConstructor;
    corexExcalidrawHost?: HostApi;
  }
}

const EMPTY_SCENE: SceneState = Object.freeze({
  type: "excalidraw",
  elements: [],
  appState: {},
  files: {},
});

const WEBCHANNEL_SCRIPT_URL = "qwebchannel.js";
const WEBCHANNEL_SCRIPT_ID = "corex-qtwebchannel-script";
const WEBCHANNEL_TRANSPORT_TIMEOUT_MS = 2500;
const WEBCHANNEL_SCRIPT_LOAD_TIMEOUT_MS = 2500;
const WEBCHANNEL_BRIDGE_TIMEOUT_MS = 5000;
const BRIDGE_CALL_TIMEOUT_MS = 15000;
const WEBCHANNEL_POLL_MS = 50;
const INITIAL_CONTENT_FRAME_ATTEMPTS = 20;
const PREVIEW_MAX_EDGE = 2048;
const DOCUMENT_APP_STATE_KEYS = [
  "gridModeEnabled",
  "gridSize",
  "gridStep",
  "viewBackgroundColor",
] as const;

let webChannelScriptLoad: Promise<boolean> | null = null;

function isRecord(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toJsonCompatible<T>(value: T): unknown {
  if (value === undefined) {
    return undefined;
  }
  return JSON.parse(
    JSON.stringify(value, (_key, item) => {
      if (item instanceof Map) {
        return Object.fromEntries(item.entries());
      }
      if (item instanceof Set) {
        return Array.from(item.values());
      }
      if (typeof item === "number" && !Number.isFinite(item)) {
        return null;
      }
      if (
        typeof item === "function" ||
        typeof item === "symbol" ||
        typeof item === "undefined"
      ) {
        return undefined;
      }
      return item;
    }),
  );
}

function coerceSceneState(value: unknown): SceneState {
  const record = isRecord(value) ? value : {};
  const elements = Array.isArray(record.elements) ? record.elements : [];
  const appState = isRecord(record.appState) ? record.appState : {};
  const files = isRecord(record.files) ? record.files : {};
  return {
    type: "excalidraw",
    elements: (toJsonCompatible(elements) as unknown[]) ?? [],
    appState: (toJsonCompatible(appState) as JsonObject) ?? {},
    files: (toJsonCompatible(files) as JsonObject) ?? {},
  };
}

function documentAppState(appState: JsonObject): JsonObject {
  const result: JsonObject = {};
  for (const key of DOCUMENT_APP_STATE_KEYS) {
    if (key in appState) {
      const value = toJsonCompatible(appState[key]);
      if (value !== undefined) {
        result[key] = value;
      }
    }
  }
  return result;
}

function fallbackDocumentSceneState(scene: SceneState): SceneState {
  return {
    type: "excalidraw",
    elements: scene.elements,
    appState: documentAppState(scene.appState),
    files: scene.files,
  };
}

function documentSceneState(scene: SceneState): SceneState {
  try {
    const serialized = serializeAsJSON(
      scene.elements as Parameters<typeof serializeAsJSON>[0],
      scene.appState as Parameters<typeof serializeAsJSON>[1],
      scene.files as Parameters<typeof serializeAsJSON>[2],
      "local",
    );
    const document = coerceSceneState(JSON.parse(serialized));
    return { ...document, appState: documentAppState(document.appState) };
  } catch {
    return fallbackDocumentSceneState(scene);
  }
}

function normalizeSceneState(value: unknown): SceneState {
  return documentSceneState(coerceSceneState(value));
}

function sceneFromEditorChange(
  elements: readonly unknown[],
  appState: JsonObject,
  files: JsonObject,
): SceneState {
  return normalizeSceneState({
    type: "excalidraw",
    elements,
    appState,
    files,
  });
}

function scheduleInitialContentFrame(api: ExcalidrawApi): void {
  let attempts = 0;
  const frameWhenReady = () => {
    const rootElement = document.getElementById("root");
    const bounds = rootElement?.getBoundingClientRect();
    const hasSize = Boolean(bounds && bounds.width > 0 && bounds.height > 0);
    if (hasSize || attempts >= INITIAL_CONTENT_FRAME_ATTEMPTS) {
      api.refresh?.();
      api.scrollToContent?.(undefined, { animate: false });
      return;
    }
    attempts += 1;
    window.requestAnimationFrame(frameWhenReady);
  };
  window.requestAnimationFrame(frameWhenReady);
}

function qwebChannelTransport(): unknown {
  return window.qt && "webChannelTransport" in window.qt
    ? window.qt.webChannelTransport
    : undefined;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

async function waitForWebChannelTransport(): Promise<boolean> {
  const deadline = Date.now() + WEBCHANNEL_TRANSPORT_TIMEOUT_MS;
  while (!qwebChannelTransport() && Date.now() < deadline) {
    await delay(WEBCHANNEL_POLL_MS);
  }
  return Boolean(qwebChannelTransport());
}

async function ensureWebChannelScript(): Promise<boolean> {
  if (typeof window.QWebChannel === "function") {
    return true;
  }
  if (!(await waitForWebChannelTransport())) {
    return false;
  }
  if (typeof window.QWebChannel === "function") {
    return true;
  }
  if (!webChannelScriptLoad) {
    webChannelScriptLoad = new Promise<boolean>((resolve) => {
      let settled = false;
      let timeoutId: number | undefined;
      const finish = () => {
        if (settled) {
          return;
        }
        settled = true;
        if (timeoutId !== undefined) {
          window.clearTimeout(timeoutId);
        }
        resolve(typeof window.QWebChannel === "function");
      };
      timeoutId = window.setTimeout(finish, WEBCHANNEL_SCRIPT_LOAD_TIMEOUT_MS);
      const existingScript = document.getElementById(WEBCHANNEL_SCRIPT_ID) as HTMLScriptElement | null;
      const script = existingScript ?? document.createElement("script");
      script.addEventListener("load", finish, { once: true });
      script.addEventListener("error", finish, { once: true });
      if (!existingScript) {
        script.id = WEBCHANNEL_SCRIPT_ID;
        script.src = new URL(WEBCHANNEL_SCRIPT_URL, window.location.href).toString();
        document.head.appendChild(script);
      }
    });
  }
  return webChannelScriptLoad;
}

function bridgeFromChannel(channel: QWebChannelInstance): BridgeObject | null {
  const objects = channel.objects ?? {};
  return objects.webSurfaceBridge ?? Object.values(objects)[0] ?? null;
}

async function resolveBridge(): Promise<BridgeObject | null> {
  if (!(await ensureWebChannelScript())) {
    return null;
  }
  const transport = qwebChannelTransport();
  if (!transport || typeof window.QWebChannel !== "function") {
    return null;
  }
  return new Promise<BridgeObject | null>((resolve) => {
    new window.QWebChannel!(transport, (channel) => {
      const deadline = Date.now() + WEBCHANNEL_BRIDGE_TIMEOUT_MS;
      const finishWhenBridgeAppears = () => {
        const bridge = bridgeFromChannel(channel);
        if (bridge || Date.now() >= deadline) {
          resolve(bridge);
          return;
        }
        window.setTimeout(finishWhenBridgeAppears, WEBCHANNEL_POLL_MS);
      };
      finishWhenBridgeAppears();
    });
  });
}

function bridgeCall<T>(
  bridge: BridgeObject | null,
  methodName: keyof BridgeObject,
  ...args: unknown[]
): Promise<T | undefined> {
  if (!bridge) {
    return Promise.resolve(undefined);
  }
  const method = bridge[methodName];
  if (typeof method !== "function") {
    return Promise.resolve(undefined);
  }
  return new Promise<T | undefined>((resolve) => {
    let settled = false;
    let timeoutId: number | undefined;
    const finish = (value: unknown) => {
      if (settled) {
        return;
      }
      settled = true;
      if (timeoutId !== undefined) {
        window.clearTimeout(timeoutId);
        timeoutId = undefined;
      }
      resolve(value as T);
    };
    if (!["save_scene", "commit_snapshot", "finish_close", "finish_without_preview"].includes(methodName)) {
      timeoutId = window.setTimeout(() => finish(undefined), BRIDGE_CALL_TIMEOUT_MS);
    }
    try {
      const result = (method as (...params: unknown[]) => unknown).apply(bridge, [
        ...args,
        finish,
      ]);
      if (result !== undefined) {
        finish(result);
      }
    } catch {
      finish(undefined);
    }
  });
}

async function loadInitialScene(bridge: BridgeObject | null): Promise<SceneState> {
  const loaded =
    (await bridgeCall<unknown>(bridge, "load_state")) ??
    bridge?.scene_state;
  if (!isRecord(loaded)) throw new Error("Drawing could not be loaded. Reopen the editor to retry.");
  return hydrateArtifactFiles(normalizeSceneState(loaded), bridge);
}

function artifactAssetId(fileId: string, fileValue: unknown): string {
  if (!isRecord(fileValue)) {
    return "";
  }
  for (const key of ["asset_id", "assetId", "artifact_id", "artifactId", "ref"]) {
    const value = fileValue[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
  }
  for (const key of ["artifact_ref", "artifactRef"]) {
    const value = fileValue[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
    if (isRecord(value) && typeof value.uri === "string" && value.uri.trim().length > 0) {
      return value.uri.trim();
    }
  }
  return fileId.startsWith("artifact://") ? fileId : "";
}

async function hydrateArtifactFiles(
  scene: SceneState,
  bridge: BridgeObject | null,
): Promise<SceneState> {
  if (!bridge || typeof bridge.asset_request !== "function") {
    return scene;
  }
  const files = { ...scene.files };
  const updates = await Promise.all(
    Object.entries(files).map(async ([fileId, fileValue]) => {
      if (!isRecord(fileValue) || typeof fileValue.dataURL === "string") {
        return null;
      }
      const assetId = artifactAssetId(fileId, fileValue);
      if (!assetId) {
        return null;
      }
      const response = await bridgeCall<JsonObject>(bridge, "asset_request", assetId);
      if (!isRecord(response) || response.ok !== true || typeof response.data_url !== "string") {
        return null;
      }
      return [
        fileId,
        {
          ...fileValue,
          dataURL: response.data_url,
          mimeType:
            typeof response.mime_type === "string" && response.mime_type
              ? response.mime_type
              : fileValue.mimeType,
        },
      ] as const;
    }),
  );
  for (const update of updates) {
    if (update) {
      files[update[0]] = update[1];
    }
  }
  return { ...scene, files };
}

function dataUrlFromBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("Preview export failed."));
    reader.readAsDataURL(blob);
  });
}

function imageSizeFromDataUrl(dataUrl: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () =>
      resolve({
        width: image.naturalWidth || image.width || 0,
        height: image.naturalHeight || image.height || 0,
      });
    image.onerror = () => resolve({ width: 0, height: 0 });
    image.src = dataUrl;
  });
}

async function createExcalidrawPreviewPayload(scene: SceneState): Promise<JsonObject> {
  const blob = await exportToBlob({
    elements: scene.elements as never[],
    appState: {
      ...scene.appState,
      exportBackground: true,
      exportEmbedScene: false,
      exportWithDarkMode: false,
      viewBackgroundColor:
        typeof scene.appState.viewBackgroundColor === "string"
          ? scene.appState.viewBackgroundColor
          : "#ffffff",
    },
    files: scene.files,
    mimeType: "image/png",
    maxWidthOrHeight: PREVIEW_MAX_EDGE,
  });
  const dataUrl = await dataUrlFromBlob(blob);
  const size = await imageSizeFromDataUrl(dataUrl);
  return {
    ok: true,
    type: "excalidraw_preview",
    mime_type: blob.type || "image/png",
    width: size.width,
    height: size.height,
    data_url: dataUrl,
  };
}

function App(): React.ReactElement {
  const [initialScene, setInitialScene] = useState<SceneState | null>(null);
  const [status, setStatus] = useState("Loading local Excalidraw editor...");
  const [readOnly, setReadOnly] = useState(false);
  const controller = useRef<SnapshotController<SceneState> | null>(null);
  const initialContentFramed = useRef(false);

  useEffect(() => {
    let cancelled = false;
    resolveBridge()
      .then(async (bridge) => {
        if (cancelled) return;
        if (!bridge) throw new Error("The drawing connection is unavailable. Reopen the editor to retry.");
        const scene = await loadInitialScene(bridge);
        if (cancelled) return;
        if ((await bridgeCall<boolean>(bridge, "start_editor")) !== true) throw new Error("The drawing connection is unavailable. Reopen the editor to retry.");
        if (cancelled) return;
        const snapshots = new SnapshotController(scene, {
          save: async (scene_state, revision) => (await bridgeCall<boolean>(bridge, "save_scene", { scene_state, revision })) === true,
          render: createExcalidrawPreviewPayload,
          persist: async (payload) => (await bridgeCall<SnapshotResult>(bridge, "commit_snapshot", payload)) ?? { ok: false, error: "Preview storage did not respond." },
          changed: (revision) => bridge.note_revision?.(revision),
          status: (payload) => bridge.snapshot_status?.(payload),
          close: async (result) => (await bridgeCall<boolean>(bridge, "finish_close", result)) === true,
          recover: async (payload) => (await bridgeCall<boolean>(bridge, "finish_without_preview", payload)) === true,
          lock: setReadOnly,
          display: setStatus,
        });
        controller.current = snapshots;
        window.corexExcalidrawHost = {
          bridgeReady: () => true,
          flushSave: () => snapshots.flushSave(),
          getSceneState: () => snapshots.getScene(),
          requestClose: () => snapshots.requestClose(),
          retryPreview: () => snapshots.retry(),
          closeWithoutPreview: () => { void snapshots.recover("close"); },
          reloadEditor: () => { void snapshots.recover("reload"); },
        };
        setInitialScene(scene);
        setStatus("Connected to local COREX bridge.");
      })
      .catch((error: unknown) => {
        if (!cancelled) setStatus(error instanceof Error ? error.message : String(error));
      });
    return () => {
      cancelled = true;
      controller.current?.dispose();
      controller.current = null;
      delete window.corexExcalidrawHost;
    };
  }, []);

  const onChange = useCallback(
    (elements: readonly unknown[], appState: JsonObject, files: JsonObject) => {
      controller.current?.change(sceneFromEditorChange(elements, appState, files));
    }, [],
  );

  const onExcalidrawApi = useCallback(
    (api: ExcalidrawApi) => {
      if (initialContentFramed.current || !initialScene || initialScene.elements.length === 0) {
        return;
      }
      initialContentFramed.current = true;
      scheduleInitialContentFrame(api);
    },
    [initialScene],
  );

  if (!initialScene) {
    return (
      <main className="corex-loading" aria-live="polite">
        <h1>Excalidraw</h1>
        <p>{status}</p>
      </main>
    );
  }

  return (
    <main className="corex-editor" aria-label="COREX Excalidraw editor">
      <div className="corex-status" aria-live="polite">
        {status}
      </div>
      <Excalidraw
        viewModeEnabled={readOnly}
        initialData={{
          elements: initialScene.elements as never[],
          appState: initialScene.appState,
          files: initialScene.files,
          scrollToContent: true,
        }}
        excalidrawAPI={onExcalidrawApi}
        onChange={onChange}
      />
    </main>
  );
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Missing Excalidraw host root element.");
}

createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
