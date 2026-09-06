import type { RpcMessage, RpcNotification, RpcResponse } from "../protocol/types";

export class RpcError extends Error {
  code: number;
  constructor(message: string, code = -32000) {
    super(message);
    this.code = code;
  }
}

export function wsUrl(): string {
  const fromShell = window.harness?.wsUrl;
  if (fromShell) return fromShell;
  return import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8765";
}

export class RpcClient {
  private ws: WebSocket | null = null;
  private nextId = 0;
  private pending = new Map<
    number,
    { resolve: (value: unknown) => void; reject: (err: Error) => void }
  >();
  private listeners = new Set<(note: RpcNotification) => void>();

  get connected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  onNotification(fn: (note: RpcNotification) => void): () => void {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  }

  async connect(url: string = wsUrl()): Promise<void> {
    if (this.connected) return;
    await this.close();
    this.ws = await new Promise<WebSocket>((resolve, reject) => {
      const socket = new WebSocket(url);
      const onErr = () => reject(new RpcError(`connect failed: ${url}`));
      socket.addEventListener("open", () => resolve(socket), { once: true });
      socket.addEventListener("error", onErr, { once: true });
    });
    this.ws.addEventListener("message", (ev) => this.handleRaw(String(ev.data)));
    this.ws.addEventListener("close", () => {
      const err = new RpcError("disconnected");
      for (const [, waiter] of this.pending) waiter.reject(err);
      this.pending.clear();
      this.ws = null;
    });
  }

  async close(): Promise<void> {
    if (!this.ws) return;
    const socket = this.ws;
    this.ws = null;
    socket.close();
  }

  async request(method: string, params: Record<string, unknown> = {}): Promise<unknown> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new RpcError("Not connected");
    }
    const id = ++this.nextId;
    const payload = JSON.stringify({ jsonrpc: "2.0", id, method, params });
    return await new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws!.send(payload);
    });
  }

  private handleRaw(raw: string): void {
    let msg: RpcMessage;
    try {
      msg = JSON.parse(raw) as RpcMessage;
    } catch {
      return;
    }
    if ("method" in msg && !("id" in msg)) {
      for (const fn of this.listeners) fn(msg);
      return;
    }
    if ("id" in msg && !("method" in msg)) {
      const waiter = this.pending.get(Number(msg.id));
      if (!waiter) return;
      this.pending.delete(Number(msg.id));
      const res = msg as RpcResponse;
      if (res.error) waiter.reject(new RpcError(res.error.message, res.error.code));
      else waiter.resolve(res.result);
    }
  }
}

let singleton: RpcClient | null = null;

export function getClient(): RpcClient {
  singleton ??= new RpcClient();
  return singleton;
}
