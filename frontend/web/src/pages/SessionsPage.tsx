import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { ThreadInfo } from "../protocol/types";
import { useHarness } from "../store/session";

function formatWhen(raw: string): string {
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString();
}

function SessionRow({ item, archived }: { item: ThreadInfo; archived: boolean }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.title);
  const navigate = useNavigate();
  const renameThread = useHarness((s) => s.renameThread);
  const deleteThread = useHarness((s) => s.deleteThread);
  const archiveThread = useHarness((s) => s.archiveThread);
  const unarchiveThread = useHarness((s) => s.unarchiveThread);

  function commit() {
    const next = draft.trim();
    setEditing(false);
    if (!next || next === item.title) return;
    void renameThread(item.thread_id, next);
  }

  return (
    <div className={`row${archived ? " archived" : ""}`}>
      {editing ? (
        <input
          className="rename"
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") setEditing(false);
          }}
        />
      ) : (
        <button
          type="button"
          className="btn secondary"
          style={{ flex: 1, textAlign: "left", minWidth: 0 }}
          onClick={() => navigate(`/chat?thread=${item.thread_id}`)}
          onDoubleClick={() => {
            setDraft(item.title);
            setEditing(true);
          }}
        >
          <div>{item.title || "未命名"}</div>
          <div className="hint">
            {item.workspace} · {formatWhen(item.updated_at) || item.thread_id.slice(0, 8)}
          </div>
        </button>
      )}
      <button
        type="button"
        className="btn secondary"
        onClick={() => {
          setDraft(item.title);
          setEditing(true);
        }}
      >
        重命名
      </button>
      {archived ? (
        <button type="button" className="btn secondary" onClick={() => void unarchiveThread(item.thread_id)}>
          恢复
        </button>
      ) : (
        <button type="button" className="btn secondary" onClick={() => void archiveThread(item.thread_id)}>
          归档
        </button>
      )}
      <button
        type="button"
        className="btn danger"
        onClick={() => {
          if (window.confirm(`删除「${item.title || "未命名"}」？对话记录一起删掉，不能恢复。`)) {
            void deleteThread(item.thread_id);
          }
        }}
      >
        删除
      </button>
    </div>
  );
}

export default function SessionsPage() {
  const navigate = useNavigate();
  const threads = useHarness((s) => s.threads);
  const workspace = useHarness((s) => s.workspace);
  const connected = useHarness((s) => s.connected);
  const refreshThreads = useHarness((s) => s.refreshThreads);
  const newDraft = useHarness((s) => s.newDraft);

  useEffect(() => {
    if (connected) void refreshThreads();
  }, [connected, refreshThreads]);

  const active = threads.filter((item) => !item.archived);
  const archived = threads.filter((item) => item.archived);

  return (
    <>
      <header>
        <div>
          <h1>Sessions</h1>
          <p>归档 = 从进行中藏起来，记录还在，随时恢复；删除 = 元数据和对话记录一起清掉，不可撤销。</p>
        </div>
        <button
          type="button"
          className="btn"
          disabled={!connected || !workspace}
          onClick={() => {
            newDraft();
            navigate("/chat");
          }}
        >
          新会话
        </button>
      </header>
      <main className="list">
        {!connected ? <p className="hint">未连接 App Server。</p> : null}
        <h2 className="section-title">进行中 · {active.length}</h2>
        {!active.length ? <p className="hint">没有进行中的会话。用过 CLI 的会列在这里（需同一份 server）。</p> : null}
        {active.map((item) => (
          <SessionRow key={item.thread_id} item={item} archived={false} />
        ))}
        <h2 className="section-title">已归档 · {archived.length}</h2>
        {!archived.length ? <p className="hint">还没有归档。归档不是删除，随时可恢复。</p> : null}
        {archived.map((item) => (
          <SessionRow key={item.thread_id} item={item} archived />
        ))}
      </main>
    </>
  );
}
