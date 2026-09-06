import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { ThreadInfo } from "../protocol/types";
import { useHarness } from "../store/session";

function label(item: ThreadInfo): string {
  return item.title || `未命名 ${item.thread_id.slice(0, 6)}`;
}

export default function SessionNav() {
  const [open, setOpen] = useState(true);
  const [editing, setEditing] = useState("");
  const [draft, setDraft] = useState("");
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

  function commit(threadId: string) {
    const next = draft.trim();
    setEditing("");
    const before = threads.find((item) => item.thread_id === threadId);
    if (!next || next === before?.title) return;
    void renameThread(threadId, next);
  }

  return (
    <section className="sessions-nav">
      <div className="head">
        <button type="button" className="toggle" onClick={() => setOpen(!open)}>
          <span className={`caret${open ? " open" : ""}`}>▸</span>
          Sessions
          <span className="count">{active.length}</span>
        </button>
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
          ＋
        </button>
      </div>
      {open ? (
        <div className="items">
          {!current ? <div className="item active draft">新会话 · 未创建</div> : null}
          {!active.length ? <p className="hint">还没有会话</p> : null}
          {active.map((item) => {
            const selected = current?.thread_id === item.thread_id;
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
                  {label(item)}
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
                  ✎
                </button>
              </div>
            );
          })}
          <button type="button" className="more" onClick={() => navigate("/sessions")}>
            管理全部会话
          </button>
        </div>
      ) : null}
    </section>
  );
}
