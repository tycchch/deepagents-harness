import type { ThreadInfo } from "../protocol/types";

export type DirGroup = {
  key: string;
  label: string;
  items: ThreadInfo[];
};

export function normalizeWorkspace(path: string): string {
  return path.replace(/\\/g, "/").replace(/\/+$/, "") || "/";
}

export function dirLabel(path: string, maxParts = 3): string {
  const parts = normalizeWorkspace(path)
    .split("/")
    .filter((part) => part && part !== ".");
  if (!parts.length) return "未分类";
  return parts.slice(-maxParts).join("/");
}

export function groupThreads(threads: ThreadInfo[]): DirGroup[] {
  const map = new Map<string, ThreadInfo[]>();
  for (const item of threads) {
    const key = normalizeWorkspace(item.workspace || "") || "/";
    const list = map.get(key) ?? [];
    list.push(item);
    map.set(key, list);
  }
  const groups = [...map.entries()].map(([key, items]) => ({
    key,
    label: key === "/" ? "未分类" : dirLabel(key),
    items: items.slice().sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || "")),
  }));
  groups.sort((a, b) => (b.items[0]?.updated_at || "").localeCompare(a.items[0]?.updated_at || ""));
  return groups;
}

export function visibleInGroup(
  items: ThreadInfo[],
  collapsed: boolean,
  currentId: string,
): ThreadInfo[] {
  if (!collapsed) return items;
  return items.filter((item) => item.thread_id === currentId);
}

export function relTime(raw: string): string {
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return "";
  const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60_000));
  if (minutes < 60) return `${Math.max(1, minutes)}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo`;
  return `${Math.floor(months / 12)}y`;
}
