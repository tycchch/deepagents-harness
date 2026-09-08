import { create } from "zustand";
import { getClient, RpcError, wsUrl } from "../lib/rpc";
import { PROTOCOL_VERSION } from "../protocol/types";
import type {
  ApprovalDecision,
  ApprovalRequestParams,
  ConfigMap,
  ItemEvent,
  ModelsState,
  ItemType,
  RpcNotification,
  SkillInfo,
  ThreadInfo,
} from "../protocol/types";

const WORKSPACE_KEY = "harness.workspace";
const THREAD_KEY = "harness.thread";

export type ChatItem = ItemEvent & { pending?: boolean };

type HarnessState = {
  connected: boolean;
  connecting: boolean;
  error: string;
  workspace: string;
  thread: ThreadInfo | null;
  threads: ThreadInfo[];
  items: ChatItem[];
  busy: boolean;
  approval: ApprovalRequestParams | null;
  skills: SkillInfo[];
  config: ConfigMap;
  models: ModelsState;
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
  setWorkspace: (path: string) => Promise<void>;
  refreshThreads: () => Promise<void>;
  startThread: (workspace?: string) => Promise<ThreadInfo>;
  resumeThread: (threadId: string) => Promise<ThreadInfo>;
  renameThread: (threadId: string, title: string) => Promise<void>;
  deleteThread: (threadId: string) => Promise<void>;
  newDraft: () => void;
  archiveThread: (threadId: string) => Promise<void>;
  unarchiveThread: (threadId: string) => Promise<void>;
  send: (text: string) => Promise<void>;
  interrupt: () => Promise<void>;
  resolveApproval: (decision: ApprovalDecision, editedArgs?: Record<string, unknown>) => Promise<void>;
  refreshSkills: () => Promise<void>;
  readSkill: (path: string) => Promise<string>;
  writeSkill: (path: string, content: string) => Promise<void>;
  refreshConfig: () => Promise<void>;
  setConfig: (values: ConfigMap) => Promise<void>;
  refreshModels: () => Promise<void>;
  setModel: (model: string, providerId?: string) => Promise<void>;
  upsertProvider: (provider: Record<string, unknown>) => Promise<void>;
  deleteProvider: (id: string) => Promise<void>;
};

const EMPTY_MODELS: ModelsState = { active_provider: "", active_model: "", providers: [] };

function workspaceOf(): string {
  const fromShell = window.harness?.cwd;
  if (fromShell) return fromShell;
  return localStorage.getItem(WORKSPACE_KEY) || "";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function failure(err: unknown, what: string): string {
  const reason = err instanceof RpcError ? err.message : String(err);
  if (reason.includes("Unknown method")) {
    return `${what}失败：App Server 是旧版本，重启一下 .\\start-server.ps1`;
  }
  return `${what}失败：${reason}`;
}

type SetState = (
  partial: Partial<HarnessState> | ((state: HarnessState) => Partial<HarnessState>),
) => void;

let notesBound = false;
// Server reuses item ids ("msg"/"think") per turn; scope them so turns don't merge.
let turnSeq = 0;

function applyNote(note: RpcNotification, set: SetState): void {
  const params = asRecord(note.params);
  if (note.method === "error") {
    set({ error: String(params.message ?? "server error"), busy: false });
    return;
  }
  if (note.method === "approval/request") {
    set({ approval: params as ApprovalRequestParams });
    return;
  }
  if (note.method === "turn/completed") {
    set({ busy: false });
    return;
  }
  if (!note.method.startsWith("item/")) return;
  const incoming: ChatItem = {
    item_id: `t${turnSeq}:${String(params.item_id ?? "item")}`,
    type: (params.type as ItemType) || "agent_message",
    text: (params.text as string | null | undefined) ?? "",
    tool: (params.tool as string | null | undefined) ?? null,
    path: (params.path as string | null | undefined) ?? null,
    pending: note.method !== "item/completed",
  };
  setItem(set, incoming, note.method === "item/delta");
}

async function fetchHistory(threadId: string): Promise<ChatItem[]> {
  try {
    const result = asRecord(await getClient().request("thread/history", { thread_id: threadId }));
    return ((result.items as ItemEvent[]) ?? []).map((item) => ({ ...item, pending: false }));
  } catch {
    return [];
  }
}

function setItem(
  set: (partial: Partial<HarnessState> | ((s: HarnessState) => Partial<HarnessState>)) => void,
  incoming: ChatItem,
  append: boolean,
): void {
  set((state) => {
    const idx = state.items.findIndex((item) => item.item_id === incoming.item_id);
    if (idx < 0) return { items: [...state.items, incoming] };
    const current = state.items[idx];
    const next = [...state.items];
    next[idx] = {
      ...current,
      ...incoming,
      text: append ? `${current.text ?? ""}${incoming.text ?? ""}` : (incoming.text ?? current.text),
    };
    return { items: next };
  });
}

export const useHarness = create<HarnessState>((set, get) => ({
  connected: false,
  connecting: false,
  error: "",
  workspace: workspaceOf(),
  thread: null,
  threads: [],
  items: [],
  busy: false,
  approval: null,
  skills: [],
  config: {},
  models: EMPTY_MODELS,

  connect: async () => {
    if (get().connecting || get().connected) return;
    set({ connecting: true, error: "" });
    const client = getClient();
    if (!notesBound) {
      client.onNotification((note) => applyNote(note, set));
      notesBound = true;
    }
    try {
      await client.connect(wsUrl());
      const cwd = get().workspace || "/";
      await client.request("initialize", {
        protocol_version: PROTOCOL_VERSION,
        client: "desktop",
        cwd,
      });
      set({ connected: true, connecting: false });
      await get().refreshThreads();
      await get().refreshConfig();
      await get().refreshModels();
      const last = localStorage.getItem(THREAD_KEY);
      if (last && !get().thread) {
        try {
          await get().resumeThread(last);
        } catch {
          localStorage.removeItem(THREAD_KEY);
        }
      }
    } catch (err) {
      set({
        connected: false,
        connecting: false,
        error: err instanceof RpcError ? err.message : String(err),
      });
    }
  },

  disconnect: async () => {
    await getClient().close();
    set({ connected: false, busy: false });
  },

  setWorkspace: async (path: string) => {
    const next = path.trim();
    localStorage.setItem(WORKSPACE_KEY, next);
    set({ workspace: next });
    const thread = get().thread;
    if (!thread || !get().connected || !next) return;
    try {
      const info = (await getClient().request("thread/set_workspace", {
        thread_id: thread.thread_id,
        workspace: next,
      })) as ThreadInfo;
      set((state) => ({
        error: "",
        thread: state.thread?.thread_id === info.thread_id ? info : state.thread,
        threads: state.threads.map((item) => (item.thread_id === info.thread_id ? info : item)),
      }));
    } catch (err) {
      set({ error: failure(err, "切换 workspace") });
    }
  },

  refreshThreads: async () => {
    const result = asRecord(await getClient().request("thread/list", { include_archived: true }));
    set({ threads: (result.threads as ThreadInfo[]) ?? [] });
  },

  startThread: async (workspace?: string) => {
    const ws = workspace || get().workspace;
    if (!ws) throw new RpcError("Set workspace first");
    const info = (await getClient().request("thread/start", {
      workspace: ws,
    })) as ThreadInfo;
    localStorage.setItem(THREAD_KEY, info.thread_id);
    set({ thread: info, items: [], busy: false, workspace: ws });
    await get().refreshThreads();
    return info;
  },

  resumeThread: async (threadId: string) => {
    const info = (await getClient().request("thread/resume", {
      thread_id: threadId,
    })) as ThreadInfo;
    localStorage.setItem(THREAD_KEY, info.thread_id);
    set({ thread: info, items: [], busy: false, workspace: info.workspace || get().workspace });
    const history = await fetchHistory(threadId);
    if (get().thread?.thread_id === threadId) set({ items: history });
    return info;
  },

  renameThread: async (threadId: string, title: string) => {
    try {
      const info = (await getClient().request("thread/rename", {
        thread_id: threadId,
        title,
      })) as ThreadInfo;
      set((state) => ({
        error: "",
        threads: state.threads.map((item) => (item.thread_id === info.thread_id ? info : item)),
        thread: state.thread?.thread_id === info.thread_id ? info : state.thread,
      }));
    } catch (err) {
      set({ error: failure(err, "重命名") });
    }
  },

  deleteThread: async (threadId: string) => {
    try {
      await getClient().request("thread/delete", { thread_id: threadId });
    } catch (err) {
      set({ error: failure(err, "删除") });
      return;
    }
    if (get().thread?.thread_id === threadId) {
      localStorage.removeItem(THREAD_KEY);
      set({ thread: null, items: [], busy: false });
    }
    await get().refreshThreads();
  },

  newDraft: () => {
    localStorage.removeItem(THREAD_KEY);
    set({ thread: null, items: [], busy: false, approval: null, error: "" });
  },

  archiveThread: async (threadId: string) => {
    await getClient().request("thread/archive", { thread_id: threadId });
    if (get().thread?.thread_id === threadId) {
      localStorage.removeItem(THREAD_KEY);
      set({ thread: null, items: [] });
    }
    await get().refreshThreads();
  },

  unarchiveThread: async (threadId: string) => {
    await getClient().request("thread/unarchive", { thread_id: threadId });
    await get().refreshThreads();
  },

  send: async (text: string) => {
    let thread = get().thread;
    if (!thread) {
      try {
        thread = await get().startThread();
      } catch (err) {
        set({ error: failure(err, "新建会话") });
        return;
      }
    }
    turnSeq += 1;
    set((state) => ({
      busy: true,
      error: "",
      items: [
        ...state.items,
        { item_id: `user-${Date.now()}`, type: "user_message", text, pending: false },
      ],
    }));
    try {
      await getClient().request("turn/start", { thread_id: thread.thread_id, text });
      await get().refreshThreads();
    } catch (err) {
      set({ busy: false, error: err instanceof RpcError ? err.message : String(err) });
    }
  },

  interrupt: async () => {
    const thread = get().thread;
    if (!thread) return;
    await getClient().request("turn/interrupt", { thread_id: thread.thread_id });
  },

  resolveApproval: async (decision, editedArgs) => {
    const approval = get().approval;
    if (!approval) return;
    await getClient().request("approval/resolve", {
      request_id: approval.request_id,
      decision,
      edited_args: editedArgs ?? null,
    });
    set({ approval: null });
  },

  refreshSkills: async () => {
    const result = asRecord(await getClient().request("skills/list"));
    set({ skills: (result.skills as SkillInfo[]) ?? [] });
  },

  readSkill: async (path: string) => {
    const result = asRecord(await getClient().request("skills/read", { path }));
    return String(result.content ?? "");
  },

  writeSkill: async (path: string, content: string) => {
    await getClient().request("skills/write", { path, content });
    await get().refreshSkills();
  },

  refreshConfig: async () => {
    const result = asRecord(await getClient().request("config/get"));
    set({ config: (result.config as ConfigMap) ?? {} });
  },

  setConfig: async (values: ConfigMap) => {
    const result = asRecord(await getClient().request("config/set", { values }));
    set({ config: (result.config as ConfigMap) ?? values });
  },

  refreshModels: async () => {
    try {
      const result = asRecord(await getClient().request("models/list"));
      set({
        models: {
          active_provider: String(result.active_provider ?? ""),
          active_model: String(result.active_model ?? ""),
          providers: (result.providers as ModelsState["providers"]) ?? [],
        },
      });
    } catch (err) {
      set({ error: failure(err, "读取模型") });
    }
  },

  setModel: async (model: string, providerId?: string) => {
    try {
      const result = asRecord(
        await getClient().request("models/set", {
          model,
          provider_id: providerId || null,
        }),
      );
      set({
        error: "",
        models: {
          active_provider: String(result.active_provider ?? providerId ?? ""),
          active_model: String(result.active_model ?? model),
          providers: (result.providers as ModelsState["providers"]) ?? get().models.providers,
        },
      });
    } catch (err) {
      set({ error: failure(err, "切换模型") });
    }
  },

  upsertProvider: async (provider: Record<string, unknown>) => {
    try {
      const result = asRecord(await getClient().request("providers/upsert", provider));
      set({
        error: "",
        models: {
          active_provider: String(result.active_provider ?? get().models.active_provider),
          active_model: String(result.active_model ?? get().models.active_model),
          providers: (result.providers as ModelsState["providers"]) ?? get().models.providers,
        },
      });
    } catch (err) {
      set({ error: failure(err, "保存供应商") });
    }
  },

  deleteProvider: async (id: string) => {
    try {
      const result = asRecord(await getClient().request("providers/delete", { id }));
      set({
        error: "",
        models: {
          active_provider: String(result.active_provider ?? ""),
          active_model: String(result.active_model ?? ""),
          providers: (result.providers as ModelsState["providers"]) ?? [],
        },
      });
    } catch (err) {
      set({ error: failure(err, "删除供应商") });
    }
  },
}));
