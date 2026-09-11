import assert from "node:assert/strict";
import test from "node:test";
import { SnapshotController } from "../src/snapshot-controller.ts";

const scene = (id: string) => ({ elements: [{ id }], files: {}, appState: {} });
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
async function until(predicate: () => boolean) {
  const end = Date.now() + 1500;
  while (!predicate()) {
    assert.ok(Date.now() < end, "condition did not settle");
    await new Promise((resolve) => setTimeout(resolve, 2));
  }
}
function harness(options: Record<string, unknown> = {}) {
  const renders: ReturnType<typeof deferred<Record<string, unknown>>>[] = [];
  const saved: unknown[] = [];
  const stored: Record<string, unknown>[] = [];
  const statuses: Record<string, unknown>[] = [];
  const closes: Record<string, unknown>[] = [];
  const revisions: number[] = [];
  const controller = new SnapshotController(scene("a"), {
    save: async (value, revision) => { saved.push({ value, revision }); return true; },
    render: async () => { const job = deferred<Record<string, unknown>>(); renders.push(job); return job.promise; },
    persist: async (payload) => { stored.push(payload); return { ok: true }; },
    changed: (revision) => revisions.push(revision),
    status: (payload) => statuses.push(payload),
    close: async (payload) => { closes.push(payload); return true; },
    display: () => {},
    debounceMs: 1,
    timeoutMs: 1000,
    ...options,
  });
  return { controller, renders, saved, stored, statuses, closes, revisions };
}

test("editing during export persists drawing independently and discards stale PNG", async () => {
  const h = harness();
  try {
    await until(() => h.renders.length === 1);
    h.controller.change(scene("b"));
    await until(() => h.saved.length === 2);
    assert.equal(h.renders.length, 1);
    h.renders[0].resolve({ png: "old" });
    await until(() => h.renders.length === 2);
    assert.equal(h.stored.length, 0);
    h.renders[1].resolve({ png: "new" });
    await until(() => h.stored.length === 1);
    assert.equal(h.stored[0].revision, 1);
    assert.equal(h.stored[0].png, "new");
  } finally { h.controller.dispose(); }
});

test("close waits for pending edit and only latest accepted snapshot closes", async () => {
  const h = harness({ debounceMs: 1000 });
  try {
    h.controller.change(scene("latest"));
    h.controller.requestClose();
    await until(() => h.renders.length === 1);
    assert.equal(h.closes.length, 0);
    assert.equal((h.saved[0] as { revision: number }).revision, 1);
    h.renders[0].resolve({ png: "latest" });
    await until(() => h.closes.length === 1);
    assert.equal(h.closes[0].revision, 1);
  } finally { h.controller.dispose(); }
});

test("storage failure retains drawing, stays open and allows close retry", async () => {
  let fail = true;
  const h = harness({ persist: async () => ({ ok: !fail, error: fail ? "Disk full" : "" }) });
  try {
    h.controller.requestClose();
    await until(() => h.renders.length === 1);
    h.renders[0].resolve({ png: "first" });
    await until(() => h.statuses.at(-1)?.state === "error");
    assert.equal(h.saved.length, 1);
    assert.equal(h.closes.length, 0);
    fail = false;
    h.controller.requestClose();
    await until(() => h.renders.length === 2);
    h.renders[1].resolve({ png: "retry" });
    await until(() => h.closes.length === 1);
  } finally { h.controller.dispose(); }
});

test("timeout and retry never overlap renderer and ignore its late completion", async () => {
  const h = harness({ timeoutMs: 30 });
  try {
    h.controller.requestClose();
    await until(() => h.renders.length === 1);
    await until(() => h.statuses.at(-1)?.state === "error");
    h.controller.requestClose();
    assert.equal(h.renders.length, 1);
    h.renders[0].resolve({ png: "expired" });
    await until(() => h.renders.length === 2);
    assert.equal(h.stored.length, 0);
    h.renders[1].resolve({ png: "fresh" });
    await until(() => h.closes.length === 1);
    assert.equal(h.stored[0].png, "fresh");
  } finally { h.controller.dispose(); }
});

test("empty board closes without inventing a rendered image", async () => {
  const h = harness();
  try {
    h.controller.change({ elements: [], files: {}, appState: {} });
    h.controller.requestClose();
    await until(() => h.closes.length === 1);
    assert.equal(h.renders.length, 0);
    assert.equal(h.stored[0].empty, true);
  } finally { h.controller.dispose(); }
});

test("failed drawing save cannot produce PNG or close", async () => {
  const h = harness({ save: async () => false });
  try {
    h.controller.requestClose();
    await until(() => h.statuses.at(-1)?.state === "error");
    assert.equal(h.renders.length, 0);
    assert.equal(h.stored.length, 0);
    assert.equal(h.closes.length, 0);
    assert.match(String(h.statuses.at(-1)?.error), /Keep this editor open/);
  } finally { h.controller.dispose(); }
});

test("same document change does not invalidate an accepted snapshot", async () => {
  const h = harness();
  try {
    await until(() => h.renders.length === 1);
    h.renders[0].resolve({ png: "first" });
    await until(() => h.stored.length === 1);
    h.controller.change(scene("a"));
    h.controller.requestClose();
    await until(() => h.closes.length === 1);
    assert.equal(h.revisions.length, 0);
    assert.equal(h.renders.length, 1);
  } finally { h.controller.dispose(); }
});

test("disposed editor drops callbacks", async () => {
  const h = harness();
  await until(() => h.renders.length === 1);
  h.controller.dispose();
  h.renders[0].resolve({ png: "late" });
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(h.stored.length, 0);
  assert.equal(h.closes.length, 0);
});

test("close without preview waits for latest drawing acknowledgement and locks editing", async () => {
  const saved = deferred<boolean>();
  const recovery: Record<string, unknown>[] = [];
  const locks: boolean[] = [];
  const h = harness({
    save: async () => saved.promise,
    lock: (value: boolean) => locks.push(value),
    recover: async (payload: Record<string, unknown>) => { recovery.push(payload); return true; },
  });
  try {
    h.controller.change(scene("latest"));
    const finishing = h.controller.recover("close");
    assert.deepEqual(locks, [true]);
    assert.equal(recovery.length, 0);
    saved.resolve(true);
    await finishing;
    assert.deepEqual(recovery, [{ revision: 1, action: "close" }]);
    assert.equal(h.renders.length, 0);
  } finally { h.controller.dispose(); }
});

test("reload never proceeds when the drawing save is rejected", async () => {
  const recovery: unknown[] = [];
  const h = harness({
    save: async () => false,
    recover: async (payload: unknown) => { recovery.push(payload); return true; },
  });
  try {
    await h.controller.recover("reload");
    assert.equal(recovery.length, 0);
    assert.equal(h.statuses.at(-1)?.state, "error");
  } finally { h.controller.dispose(); }
});

test("editor timestamps and mapping order do not invalidate a snapshot", async () => {
  const h = harness();
  try {
    await until(() => h.renders.length === 1);
    h.renders[0].resolve({ png: "first" });
    await until(() => h.stored.length === 1);
    h.controller.change({ appState: {}, files: {}, elements: [{ version: 5, updated: 10, id: "a" }] });
    h.controller.requestClose();
    await until(() => h.closes.length === 1);
    assert.equal(h.revisions.length, 0);
    assert.equal(h.renders.length, 1);
  } finally { h.controller.dispose(); }
});
