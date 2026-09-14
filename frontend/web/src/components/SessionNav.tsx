import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, Pencil, Plus } from "lucide-react";
import { groupThreads, relTime, visibleInGroup } from "../lib/threads";
import type { ThreadInfo } from "../protocol/types";
import { useHarness } from "../store/session";

const COLLAPSED_KEY = "harness.collapsedDirs";

function label(item: ThreadInfo): string {
  return item.title || `未命名 ${item.thread_id.slice(0, 6)}`;
}

function readCollapsed(): string[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(COLLAPSED_KEY) || "[]") as unknown;
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export default function SessionNav() {
  const [editing, setEditing] = useState("");
  const [draft, setDraft] = useState("");
  const [collapsed, setCollapsed] = useState<string[]>(readCollapsed);
  const navigate = useNavigate();
  const threads = useHarness((s) => s.threads);
  const current = useHarness((s) => s.thread);
  const connected = useHarness((s) => s.connected);
  const workspace = useHarness((s) => s.workspace);
  const refreshThreads = useHarness((s) => s.refreshThreads);
  const renameThread = useHarness((s) => s.renameThread);
  const newDraft = useHarness((s) => s.newDraft);

  useEffect(() => {
    if (connected) void refreshThreads();
  }, [connected, refreshThreads]);

  const active = threads.filter((item) => !item.archived);
  const groups = groupThreads(active);
  const currentId = current?.thread_id || "";

  function toggleDir(key: string) {
    setCollapsed((prev) => {
      const next = prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key];
      localStorage.setItem(COLLAPSED_KEY, JSON.stringify(next));
      return next;
    });
  }

  function commit(threadId: string) {
    const next = draft.trim();
    setEditing("");
    const before = threads.find((item) => item.thread_id === threadId);
    if (!next || next === before?.title) return;
    void renameThread(threadId, next);
  }

  function renderItem(item: ThreadInfo) {
    const selected = currentId === item.thread_id;
    if (editing === item.thread_id) {
      return (
        <input
          key={item.thread_id}
          className="rename"
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => commit(item.thread_id)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit(item.thread_id);
            if (e.key === "Escape") setEditing("");
          }}
        />
      );
    }
    return (
      <div key={item.thread_id} className={`item${selected ? " active" : ""}`}>
        <button
          type="button"
          className="open"
          title={label(item)}
          onClick={() => navigate(`/chat?thread=${item.thread_id}`)}
          onDoubleClick={() => {
            setDraft(item.title);
            setEditing(item.thread_id);
          }}
        >
          <span className="item-title">{label(item)}</span>
          <span className="item-when">{relTime(item.updated_at)}</span>
        </button>
        <button
          type="button"
          className="icon"
          title="重命名"
          onClick={() => {
            setDraft(item.title);
            setEditing(item.thread_id);
          }}
        >
          <Pencil size={12} aria-hidden />
        </button>
      </div>
    );
  }

  return (
    <section className="sessions-nav">
      <div className="head">
        <span className="toggle-title">会话</span>
        <span className="count">{active.length}</span>
        <button
          type="button"
          className="icon"
          title="新会话（发第一条消息时才创建）"
          disabled={!connected || !workspace}
          onClick={() => {
            newDraft();
            navigate("/chat");
          }}
        >
          <Plus size={14} aria-hidden />
        </button>
      </div>
      <div className="items">
        {!current ? <div className="item active draft">新会话 · 未创建</div> : null}
        {!active.length ? <p className="hint">还没有会话</p> : null}
        {groups.map((group) => {
          const folded = collapsed.includes(group.key);
          const shown = visibleInGroup(group.items, folded, currentId);
          return (
            <div key={group.key} className={`dir-group${folded ? " folded" : ""}`}>
              <div className="dir-head">
                <button
                  type="button"
                  className="dir-fold"
                  title={folded ? "展开此目录" : "折叠此目录"}
                  aria-expanded={!folded}
                  onClick={() => toggleDir(group.key)}
                >
                  <ChevronRight size={13} className={`caret${folded ? "" : " open"}`} aria-hidden />
                </button>
                <span className="dir-label" title={group.key}>
                  {group.label}
                </span>
              </div>
              {shown.map(renderItem)}
            </div>
          );
        })}
        <button type="button" className="more" onClick={() => navigate("/sessions")}>
          管理全部会话
        </button>
      </div>
    </section>
  );
}
