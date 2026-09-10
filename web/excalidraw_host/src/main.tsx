import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Excalidraw,
  exportToBlob,
  serializeAsJSON,
} from "@excalidraw/excalidraw";
import "@excalidraw/excalidraw/index.css";
import "./styles.css";

type JsonObject = Record<string, unknown>;
type SceneState = {
  type: "excalidraw";
  elements: unknown[];
  appState: JsonObject;
  files: JsonObject;
};

type BridgeObject = {
  load_state?: (callback: (value: unknown) => void) => unknown;
  save_state?: (payload: unknown, callback?: (value: unknown) => void) => unknown;
  asset_request?: (assetId: string, callback?: (value: unknown) => void) => unknown;
  export_preview?: (payload?: unknown, callback?: (value: unknown) => void) => unknown;
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

type PreviewExportResult = JsonObject & {
  ok: boolean;
};

type ExcalidrawApi = {
  refresh?: () => void;
  scrollToContent?: (target?: unknown, opts?: JsonObject) => void;
};

type HostApi = {
  version: string;
  bridgeReady: () => boolean;
  flushSave: () => Promise<boolean>;
  getSceneState: () => SceneState;
  exportPreview: (options?: JsonObject) => Promise<PreviewExportResult>;
  requestPreviewExport: (options?: JsonObject) => Promise<PreviewExportResult>;
};

declare global {
  interface Window {
    qt?: { webChannelTransport?: unknown };
    QWebChannel?: QWebChannelConstructor;
    corexExcalidrawHost?: HostApi;
    corexExcalidrawExportPreview?: (options?: JsonObject) => Promise<PreviewExportResult>;
  }
}

const EMPTY_SCENE: SceneState = Object.freeze({
  type: "excalidraw",
  elements: [],
  appState: {},
  files: {},
});

const SAVE_DEBOUNCE_MS = 350;
const WEBCHANNEL_SCRIPT_URL = "qwebchannel.js";
const WEBCHANNEL_SCRIPT_ID = "corex-qtwebchannel-script";
const WEBCHANNEL_TRANSPORT_TIMEOUT_MS = 2500;
const WEBCHANNEL_SCRIPT_LOAD_TIMEOUT_MS = 2500;
const WEBCHANNEL_BRIDGE_TIMEOUT_MS = 5000;
const BRIDGE_CALL_TIMEOUT_MS = 750;
const WEBCHANNEL_POLL_MS = 50;
const INITIAL_CONTENT_FRAME_ATTEMPTS = 20;
const PREVIEW_EXPORT_TIMEOUT_MS = 3500;
const FALLBACK_PREVIEW_MAX_WIDTH = 960;
const FALLBACK_PREVIEW_MAX_HEIGHT = 540;
const FALLBACK_PREVIEW_PADDING = 32;
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
    return coerceSceneState(JSON.parse(serialized));
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
    timeoutId = window.setTimeout(() => {
      finish(undefined);
    }, BRIDGE_CALL_TIMEOUT_MS);
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
    bridge?.scene_state ??
    EMPTY_SCENE;
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

function finiteNumber(value: unknown, fallback = 0): number {
  const numberValue = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
}

function textValue(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim().length > 0 ? value : fallback;
}

function elementPoints(element: JsonObject): Array<[number, number]> {
  if (!Array.isArray(element.points)) {
    return [];
  }
  return element.points
    .filter((point): point is unknown[] => Array.isArray(point) && point.length >= 2)
    .map((point) => [finiteNumber(point[0]), finiteNumber(point[1])]);
}

function elementBounds(element: JsonObject): { minX: number; minY: number; maxX: number; maxY: number } {
  const x = finiteNumber(element.x);
  const y = finiteNumber(element.y);
  const width = Math.max(1, finiteNumber(element.width, 1));
  const height = Math.max(1, finiteNumber(element.height, 1));
  let minX = x;
  let minY = y;
  let maxX = x + width;
  let maxY = y + height;
  for (const [pointX, pointY] of elementPoints(element)) {
    minX = Math.min(minX, x + pointX);
    minY = Math.min(minY, y + pointY);
    maxX = Math.max(maxX, x + pointX);
    maxY = Math.max(maxY, y + pointY);
  }
  return { minX, minY, maxX, maxY };
}

function sceneContentBounds(elements: unknown[]): { minX: number; minY: number; maxX: number; maxY: number } {
  const visibleElements = elements.filter(
    (element): element is JsonObject => isRecord(element) && element.isDeleted !== true,
  );
  if (visibleElements.length === 0) {
    return { minX: 0, minY: 0, maxX: 640, maxY: 360 };
  }
  const first = elementBounds(visibleElements[0]);
  return visibleElements.slice(1).reduce((bounds, element) => {
    const next = elementBounds(element);
    return {
      minX: Math.min(bounds.minX, next.minX),
      minY: Math.min(bounds.minY, next.minY),
      maxX: Math.max(bounds.maxX, next.maxX),
      maxY: Math.max(bounds.maxY, next.maxY),
    };
  }, first);
}

function fallbackCanvasSize(bounds: { minX: number; minY: number; maxX: number; maxY: number }): {
  width: number;
  height: number;
  scale: number;
} {
  const contentWidth = Math.max(1, bounds.maxX - bounds.minX);
  const contentHeight = Math.max(1, bounds.maxY - bounds.minY);
  const scale = Math.min(
    2,
    (FALLBACK_PREVIEW_MAX_WIDTH - FALLBACK_PREVIEW_PADDING * 2) / contentWidth,
    (FALLBACK_PREVIEW_MAX_HEIGHT - FALLBACK_PREVIEW_PADDING * 2) / contentHeight,
  );
  return {
    width: Math.max(320, Math.ceil(contentWidth * scale + FALLBACK_PREVIEW_PADDING * 2)),
    height: Math.max(180, Math.ceil(contentHeight * scale + FALLBACK_PREVIEW_PADDING * 2)),
    scale,
  };
}

function drawLinearElement(context: CanvasRenderingContext2D, element: JsonObject): void {
  const x = finiteNumber(element.x);
  const y = finiteNumber(element.y);
  const points = elementPoints(element);
  if (points.length === 0) {
    return;
  }
  context.beginPath();
  context.moveTo(x + points[0][0], y + points[0][1]);
  for (const [pointX, pointY] of points.slice(1)) {
    context.lineTo(x + pointX, y + pointY);
  }
  context.stroke();
  if (element.type !== "arrow" || points.length < 2) {
    return;
  }
  const [fromX, fromY] = points[points.length - 2];
  const [toX, toY] = points[points.length - 1];
  const angle = Math.atan2(toY - fromY, toX - fromX);
  const arrowLength = 14;
  context.beginPath();
  context.moveTo(x + toX, y + toY);
  context.lineTo(
    x + toX - arrowLength * Math.cos(angle - Math.PI / 6),
    y + toY - arrowLength * Math.sin(angle - Math.PI / 6),
  );
  context.moveTo(x + toX, y + toY);
  context.lineTo(
    x + toX - arrowLength * Math.cos(angle + Math.PI / 6),
    y + toY - arrowLength * Math.sin(angle + Math.PI / 6),
  );
  context.stroke();
}

function drawFallbackElement(context: CanvasRenderingContext2D, element: JsonObject): void {
  if (element.isDeleted === true) {
    return;
  }
  const x = finiteNumber(element.x);
  const y = finiteNumber(element.y);
  const width = Math.max(1, finiteNumber(element.width, 1));
  const height = Math.max(1, finiteNumber(element.height, 1));
  const type = textValue(element.type);
  const strokeColor = textValue(element.strokeColor, "#1e1e1e");
  const backgroundColor = textValue(element.backgroundColor, "transparent");
  const opacity = Math.max(0, Math.min(1, finiteNumber(element.opacity, 100) / 100));
  context.save();
  context.globalAlpha = opacity;
  context.strokeStyle = strokeColor;
  context.fillStyle = backgroundColor;
  context.lineWidth = Math.max(1, finiteNumber(element.strokeWidth, 1));
  context.lineCap = "round";
  context.lineJoin = "round";

  if (backgroundColor && backgroundColor !== "transparent") {
    if (type === "ellipse") {
      context.beginPath();
      context.ellipse(x + width / 2, y + height / 2, width / 2, height / 2, 0, 0, Math.PI * 2);
      context.fill();
    } else if (type === "diamond") {
      context.beginPath();
      context.moveTo(x + width / 2, y);
      context.lineTo(x + width, y + height / 2);
      context.lineTo(x + width / 2, y + height);
      context.lineTo(x, y + height / 2);
      context.closePath();
      context.fill();
    } else if (type === "rectangle") {
      context.fillRect(x, y, width, height);
    }
  }

  if (type === "ellipse") {
    context.beginPath();
    context.ellipse(x + width / 2, y + height / 2, width / 2, height / 2, 0, 0, Math.PI * 2);
    context.stroke();
  } else if (type === "diamond") {
    context.beginPath();
    context.moveTo(x + width / 2, y);
    context.lineTo(x + width, y + height / 2);
    context.lineTo(x + width / 2, y + height);
    context.lineTo(x, y + height / 2);
    context.closePath();
    context.stroke();
  } else if (type === "line" || type === "arrow" || type === "freedraw") {
    drawLinearElement(context, element);
  } else if (type === "text") {
    context.fillStyle = strokeColor;
    context.font = `${Math.max(8, finiteNumber(element.fontSize, 20))}px sans-serif`;
    context.textBaseline = "top";
    context.fillText(textValue(element.text, ""), x, y);
  } else {
    context.strokeRect(x, y, width, height);
  }
  context.restore();
}

function createCanvasPreviewPayload(scene: SceneState, options: JsonObject, reason: string): JsonObject {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Canvas preview export is unavailable.");
  }
  const bounds = sceneContentBounds(scene.elements);
  const canvasSize = fallbackCanvasSize(bounds);
  canvas.width = canvasSize.width;
  canvas.height = canvasSize.height;
  context.fillStyle = textValue(scene.appState.viewBackgroundColor, "#ffffff");
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.translate(
    (canvas.width - (bounds.maxX - bounds.minX) * canvasSize.scale) / 2 - bounds.minX * canvasSize.scale,
    (canvas.height - (bounds.maxY - bounds.minY) * canvasSize.scale) / 2 - bounds.minY * canvasSize.scale,
  );
  context.scale(canvasSize.scale, canvasSize.scale);
  for (const element of scene.elements) {
    if (isRecord(element)) {
      drawFallbackElement(context, element);
    }
  }
  return {
    ok: true,
    type: "excalidraw_preview",
    mime_type: "image/png",
    width: canvas.width,
    height: canvas.height,
    data_url: canvas.toDataURL("image/png"),
    scene_state: scene,
    options,
    fallback_reason: reason,
  };
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeoutId = window.setTimeout(() => reject(new Error(message)), timeoutMs);
    promise.then(
      (value) => {
        window.clearTimeout(timeoutId);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timeoutId);
        reject(error);
      },
    );
  });
}

async function createExcalidrawPreviewPayload(scene: SceneState, options: JsonObject): Promise<JsonObject> {
  const blob = await withTimeout(exportToBlob({
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
  }), PREVIEW_EXPORT_TIMEOUT_MS, "Excalidraw preview export timed out.");
  const dataUrl = await dataUrlFromBlob(blob);
  const size = await imageSizeFromDataUrl(dataUrl);
  return {
    ok: true,
    type: "excalidraw_preview",
    mime_type: blob.type || "image/png",
    width: size.width,
    height: size.height,
    data_url: dataUrl,
    scene_state: scene,
    options,
  };
}

async function createPreviewPayload(scene: SceneState, options: JsonObject): Promise<JsonObject> {
  try {
    return await createExcalidrawPreviewPayload(scene, options);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    return createCanvasPreviewPayload(scene, options, reason);
  }
}

function normalizePreviewResult(
  hostPayload: JsonObject,
  bridgeResponse: unknown,
): PreviewExportResult {
  if (isRecord(bridgeResponse)) {
    return {
      ...bridgeResponse,
      ok: bridgeResponse.ok === true,
      host_payload: hostPayload,
    };
  }
  return {
    ...hostPayload,
    ok: true,
  };
}

function App(): React.ReactElement {
  const [bridge, setBridge] = useState<BridgeObject | null>(null);
  const [initialScene, setInitialScene] = useState<SceneState | null>(null);
  const [status, setStatus] = useState("Loading local Excalidraw editor...");
  const latestScene = useRef<SceneState>(EMPTY_SCENE);
  const pendingScene = useRef<SceneState | null>(null);
  const saveTimer = useRef<number | undefined>(undefined);
  const initialContentFramed = useRef(false);

  const saveScene = useCallback(
    async (scene: SceneState): Promise<boolean> => {
      pendingScene.current = null;
      const result = await bridgeCall<boolean>(bridge, "save_state", scene);
      return result !== false;
    },
    [bridge],
  );

  const flushSave = useCallback(async (): Promise<boolean> => {
    if (saveTimer.current !== undefined) {
      window.clearTimeout(saveTimer.current);
      saveTimer.current = undefined;
    }
    const scene = pendingScene.current;
    if (!scene) {
      return true;
    }
    return saveScene(scene);
  }, [saveScene]);

  const exportPreview = useCallback(
    async (options: JsonObject = {}): Promise<PreviewExportResult> => {
      const scene = latestScene.current;
      await flushSave();
      try {
        const hostPayload = await createPreviewPayload(scene, options);
        const bridgeResponse = await bridgeCall<JsonObject>(
          bridge,
          "export_preview",
          hostPayload,
        );
        return normalizePreviewResult(hostPayload, bridgeResponse);
      } catch (error) {
        return {
          ok: false,
          error: error instanceof Error ? error.message : String(error),
          scene_state: scene,
          host_payload: {
            scene_state: scene,
            options,
          },
        };
      }
    },
    [bridge, flushSave],
  );

  useEffect(() => {
    let cancelled = false;
    resolveBridge()
      .then(async (resolvedBridge) => {
        if (cancelled) {
          return;
        }
        setBridge(resolvedBridge);
        const scene = await loadInitialScene(resolvedBridge);
        if (cancelled) {
          return;
        }
        latestScene.current = scene;
        setInitialScene(scene);
        setStatus(
          resolvedBridge
            ? "Connected to local COREX bridge."
            : "Running without a Qt WebChannel bridge; close-save fallback active.",
        );
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setInitialScene(EMPTY_SCENE);
        setStatus(error instanceof Error ? error.message : String(error));
      });
    return () => {
      cancelled = true;
      if (saveTimer.current !== undefined) {
        window.clearTimeout(saveTimer.current);
      }
    };
  }, []);

  useEffect(() => {
    window.corexExcalidrawHost = {
      version: "p01-real-excalidraw-host",
      bridgeReady: () => bridge !== null,
      flushSave,
      getSceneState: () => latestScene.current,
      exportPreview,
      requestPreviewExport: exportPreview,
    };
    window.corexExcalidrawExportPreview = exportPreview;
  }, [bridge, exportPreview, flushSave]);

  const onChange = useCallback(
    (elements: readonly unknown[], appState: JsonObject, files: JsonObject) => {
      const scene = sceneFromEditorChange(elements, appState, files);
      latestScene.current = scene;
      pendingScene.current = scene;
      if (saveTimer.current !== undefined) {
        window.clearTimeout(saveTimer.current);
      }
      saveTimer.current = window.setTimeout(() => {
        saveTimer.current = undefined;
        void saveScene(scene);
      }, SAVE_DEBOUNCE_MS);
    },
    [saveScene],
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
