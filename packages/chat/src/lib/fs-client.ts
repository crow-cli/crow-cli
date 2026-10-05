/**
 * The `/fs` websocket client: JSON requests out, JSON replies and pushed
 * events in.
 *
 * crow-web owns the buffers — this module is only the transport. One socket
 * per browser tab, which is what makes the server's per-connection refcount
 * mean something: two tabs holding one path keep each other's unsaved work
 * alive, and a tab that vanishes gives up its claims.
 */

export type FileView = {
  /** Normalized root-relative path — the buffer key. */
  path: string;
  content: string;
  dirty: boolean;
  /** Unix millis; null when the file does not exist on disk yet. */
  mtime: number | null;
};

export type Entry = {
  name: string;
  path: string;
  type: "dir" | "file";
  size: number | null;
  mtime: number | null;
  dirty: boolean;
};

export type Tree = { path: string; entries: Entry[] };

export type CloseReply =
  | { state: "kept"; dirty: boolean }
  | { state: "dropped" };

export type Hello = { root: string; buffers: FileView[] };

export type FsMoved = {
  kind: "mkdir" | "rename" | "copy" | "delete" | "close";
  path: string;
  to: string | null;
  parent: string;
};

export type FsEvent =
  | { event: "hello"; data: Hello }
  | { event: "buffer"; data: FileView }
  | { event: "fs"; data: FsMoved };

export type Op =
  | "tree"
  | "read"
  | "write"
  | "commit"
  | "close"
  | "mkdir"
  | "rename"
  | "copy"
  | "delete"
  | "reroot"
  | "browse";

export type ConnectionState = "connecting" | "open" | "closed";

/** One flat envelope: a reply carries the request id, an event does not. */
type Frame = {
  id?: number;
  ok?: unknown;
  error?: string;
  event?: string;
  data?: unknown;
};

type Pending = {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
};

// Same origin, always: vite proxies /fs in dev, and the embedded build serves
// it from the binary that serves the page.
const socketUrl = () =>
  `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/fs`;

const BACKOFF_FLOOR = 250;
const BACKOFF_CEIL = 5_000;

export class FsClient {
  private ws: WebSocket | null = null;
  private seq = 0;
  private pending = new Map<number, Pending>();
  private eventListeners = new Set<(event: FsEvent) => void>();
  private stateListeners = new Set<(state: ConnectionState) => void>();
  private attempt = 0;
  private retry: ReturnType<typeof setTimeout> | null = null;
  private given = false;
  private current: ConnectionState = "closed";

  get state(): ConnectionState {
    return this.current;
  }

  /** Idempotent: a live or connecting socket is left alone. */
  connect() {
    if (this.retry) {
      clearTimeout(this.retry);
      this.retry = null;
    }
    this.given = false;
    const ready = this.ws?.readyState;
    if (ready === WebSocket.OPEN || ready === WebSocket.CONNECTING) return;

    this.set("connecting");
    const ws = new WebSocket(socketUrl());
    this.ws = ws;
    ws.onopen = () => {
      this.attempt = 0;
      this.set("open");
    };
    ws.onmessage = (message) => this.receive(String(message.data));
    // onerror is always followed by onclose; everything lands there.
    ws.onerror = () => ws.close();
    ws.onclose = () => {
      if (this.ws === ws) this.ws = null;
      this.failPending(new Error("the /fs socket closed"));
      this.set("closed");
      if (!this.given) this.reconnect();
    };
  }

  /** Stop for good — page teardown, or a vite HMR dispose. */
  close() {
    this.given = true;
    if (this.retry) {
      clearTimeout(this.retry);
      this.retry = null;
    }
    this.ws?.close();
    this.ws = null;
    this.failPending(new Error("the /fs client was closed"));
  }

  private reconnect() {
    const delay = Math.min(BACKOFF_CEIL, BACKOFF_FLOOR * 2 ** this.attempt);
    this.attempt += 1;
    this.retry = setTimeout(() => {
      this.retry = null;
      this.connect();
    }, delay);
  }

  private set(state: ConnectionState) {
    if (this.current === state) return;
    this.current = state;
    for (const listener of this.stateListeners) listener(state);
  }

  private failPending(error: Error) {
    const pending = [...this.pending.values()];
    this.pending.clear();
    for (const { reject } of pending) reject(error);
  }

  private receive(raw: string) {
    let frame: Frame;
    try {
      frame = JSON.parse(raw) as Frame;
    } catch {
      console.error("[fs] unparseable frame", raw);
      return;
    }
    if (frame.event) {
      const event = { event: frame.event, data: frame.data } as FsEvent;
      for (const listener of this.eventListeners) listener(event);
      return;
    }
    const pending = frame.id === undefined ? undefined : this.pending.get(frame.id);
    if (!pending) return;
    this.pending.delete(frame.id as number);
    if (frame.error) pending.reject(new Error(frame.error));
    else pending.resolve(frame.ok);
  }

  /** One request/reply round trip. Rejects with the server's error line. */
  call<T>(op: Op, params: { path?: string; to?: string; text?: string } = {}): Promise<T> {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error("the /fs socket is not open"));
    }
    const id = ++this.seq;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, {
        resolve: resolve as (value: unknown) => void,
        reject,
      });
      ws.send(JSON.stringify({ id, op, ...params }));
    });
  }

  /**
   * Resolves the moment the socket is open — immediately if it already is,
   * otherwise after whatever reconnect backoff is in flight. Callers that
   * would rather wait than fail use this before `call`.
   */
  ready(): Promise<void> {
    if (this.current === "open") return Promise.resolve();
    let off: () => void;
    return new Promise<void>((resolve) => {
      off = this.onState((state) => {
        if (state !== "open") return;
        off();
        resolve();
      });
    });
  }

  onEvent(listener: (event: FsEvent) => void): () => void {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  }

  onState(listener: (state: ConnectionState) => void): () => void {
    this.stateListeners.add(listener);
    listener(this.current);
    return () => this.stateListeners.delete(listener);
  }
}

export const fsClient = new FsClient();

// A hot reload makes a new module and a new socket; drop the old one instead
// of leaking a client id the server keeps refcounting.
if (import.meta.hot) {
  import.meta.hot.dispose(() => fsClient.close());
}
