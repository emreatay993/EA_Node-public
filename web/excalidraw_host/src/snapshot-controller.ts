// Purpose: One revision-aware owner for board save, PNG export, deadline and close.
// Map: feature_routes/excalidraw_web_host_real_editor
// Tests: web/excalidraw_host/tests/snapshot-controller.test.ts
export type SnapshotResult = Record<string, unknown> & { ok: boolean };
export type SnapshotScene = { elements: unknown[] };

type Dependencies<S> = {
  save: (scene: S, revision: number) => Promise<boolean>;
  render: (scene: S) => Promise<Record<string, unknown>>;
  persist: (payload: Record<string, unknown>) => Promise<SnapshotResult>;
  changed: (revision: number) => void;
  status: (payload: Record<string, unknown>) => void;
  close: (result: SnapshotResult) => Promise<boolean>;
  recover?: (payload: Record<string, unknown>) => Promise<boolean>;
  lock?: (locked: boolean) => void;
  display: (message: string) => void;
  debounceMs?: number;
  timeoutMs?: number;
};

type ActiveExport = { revision: number; attempt: string; expired: boolean };

function sceneContentKey(scene: SnapshotScene): string {
  return JSON.stringify(scene, (key, value) => {
    if (["version", "versionNonce", "updated", "lastRetrieved", "created"].includes(key)) return undefined;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)));
    }
    return value;
  });
}

export class SnapshotController<S extends SnapshotScene> {
  private revision = 0;
  private scene: S;
  private sceneKey: string;
  private savedRevision = -1;
  private saveTask: Promise<boolean> | null = null;
  private active: ActiveExport | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private sequence = 0;
  private closing = false;
  private disposed = false;
  private queued = false;
  private failed = false;
  private accepted: SnapshotResult | null = null;
  private recovering = false;

  constructor(scene: S, private deps: Dependencies<S>) {
    this.scene = scene;
    this.sceneKey = sceneContentKey(scene);
    this.schedule();
  }

  getScene(): S { return this.scene; }

  change(scene: S): void {
    const key = sceneContentKey(scene);
    if (key === this.sceneKey || this.disposed) return;
    this.scene = scene;
    this.sceneKey = key;
    this.revision += 1;
    this.accepted = null;
    this.failed = false;
    this.deps.changed(this.revision);
    this.report("updating");
    this.schedule();
  }

  private schedule(): void {
    clearTimeout(this.timer);
    this.queued = true;
    this.timer = setTimeout(() => {
      this.timer = undefined;
      // Drawing persistence continues even while a PNG export is active.
      void this.flushSave().then((ok) => { if (ok) this.request(); });
    }, this.deps.debounceMs ?? 500);
  }

  async flushSave(): Promise<boolean> {
    if (this.saveTask) return this.saveTask;
    this.saveTask = (async () => {
      while (!this.disposed && this.savedRevision !== this.revision) {
        const revision = this.revision;
        const scene = this.scene;
        try {
          const ok = await this.deps.save(scene, revision);
          if (!ok) {
            if (revision !== this.revision) continue;
            this.fail("Drawing could not be saved. Keep this editor open and retry.");
            return false;
          }
          this.savedRevision = revision;
        } catch {
          this.fail("Drawing could not be saved. Keep this editor open and retry.");
          return false;
        }
      }
      return !this.disposed;
    })();
    try { return await this.saveTask; }
    finally { this.saveTask = null; }
  }

  requestClose(): void {
    if (this.recovering) return;
    this.closing = true;
    this.deps.lock?.(true);
    this.request();
  }

  retry(): void { this.request(); }

  async recover(action: "close" | "reload"): Promise<void> {
    if (this.disposed || this.recovering || !this.deps.recover) return;
    this.recovering = true;
    this.closing = true;
    this.deps.lock?.(true);
    clearTimeout(this.timer);
    this.queued = false;
    if (this.active) this.active.expired = true;
    this.accepted = null;
    this.savedRevision = -1;
    this.report("closing");
    let expired = false;
    const timeout = setTimeout(() => {
      expired = true;
      this.fail("Drawing save did not finish. Keep this editor open and retry.");
    }, this.deps.timeoutMs ?? 15000);
    try {
      if (!(await this.flushSave()) || expired || this.disposed) return;
      const saved = await this.deps.recover({ revision: this.revision, action });
      if (!saved && !expired && !this.disposed) this.fail("Drawing save was not acknowledged. Keep this editor open and retry.");
    } catch {
      if (!expired && !this.disposed) this.fail("Drawing save was not acknowledged. Keep this editor open and retry.");
    } finally {
      clearTimeout(timeout);
      this.recovering = false;
    }
  }

  private request(): void {
    if (this.disposed || this.recovering) return;
    clearTimeout(this.timer);
    this.timer = undefined;
    this.failed = false;
    this.queued = true;
    if (this.active) {
      if (this.active.expired) {
        this.report("error", "The previous export is still finishing. Retry is queued; keep this editor open.");
      } else if (this.closing && this.active.revision === this.revision) {
        this.report("closing", "", this.active.attempt);
      }
      return;
    }
    if (this.accepted?.revision === this.revision) {
      this.queued = false;
      if (this.closing) void this.completeClose(this.accepted);
      return;
    }
    void this.run();
  }

  private async run(): Promise<void> {
    const job = { revision: this.revision, attempt: String(++this.sequence), expired: false };
    const scene = this.scene;
    this.active = job;
    this.queued = false;
    this.report(this.closing ? "closing" : "updating", "", job.attempt);
    const timeout = setTimeout(() => {
      if (job.expired || this.disposed) return;
      job.expired = true;
      this.fail("Preview export timed out. Your drawing is kept; retry the preview before closing.");
    }, this.deps.timeoutMs ?? 15000);
    try {
      if (!(await this.flushSave()) || !this.current(job)) return;
      const empty = !scene.elements.some((value) =>
        typeof value === "object" && value !== null && (value as Record<string, unknown>).isDeleted !== true,
      );
      const payload = empty ? { empty: true } : await this.deps.render(scene);
      if (!this.current(job)) return;
      const result = await this.deps.persist({ ...payload, revision: job.revision, attempt: job.attempt });
      if (!this.current(job)) return;
      if (!result || result.ok !== true) throw new Error(String(result?.error || "Preview could not be stored."));
      this.accepted = { ...result, revision: job.revision };
      this.failed = false;
      this.deps.display(empty ? "Empty board. Drawing saved." : "Drawing and preview saved.");
      if (this.closing) await this.completeClose(this.accepted);
    } catch (error) {
      if (this.current(job)) this.fail(error instanceof Error ? error.message : String(error));
    } finally {
      clearTimeout(timeout);
      this.active = null;
      if (!this.disposed && !this.failed && this.queued) this.request();
    }
  }

  private current(job: ActiveExport): boolean {
    return !this.disposed && !job.expired && this.revision === job.revision;
  }

  private async completeClose(result: SnapshotResult): Promise<void> {
    if (await this.deps.close(result)) {
      this.closing = false;
    } else {
      this.fail("The latest drawing needs a preview. Retry before closing.");
    }
  }

  private report(state: string, error = "", attempt = ""): void {
    if (this.disposed) return;
    this.deps.status({ revision: this.revision, state, error, attempt, closing: this.closing });
    this.deps.display(error || (this.closing ? "Saving preview before closing..." : "Updating preview..."));
  }

  private fail(error: string): void {
    this.failed = true;
    this.closing = false;
    this.accepted = null;
    this.savedRevision = -1;
    this.deps.lock?.(false);
    this.report("error", error);
  }

  dispose(): void {
    this.disposed = true;
    clearTimeout(this.timer);
  }
}
