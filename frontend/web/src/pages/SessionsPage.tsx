import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import type { ThreadInfo } from "../protocol/types";
import { useHarness } from "../store/session";

function formatWhen(raw: string): string {
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString();
}

function SessionRow({
  item,
  archived,
}: {
  item: ThreadInfo;
  archived: boolean;
}) {
  const navigate = useNavigate();
  const archiveThread = useHarness((s) => s.archiveThread);
  const unarchiveThread = useHarness((s) => s.unarchiveThread);
  return (
    <div className={`row${archived ? " archived" : ""}`}>
      <button
        type="button"
        className="btn secondary"
        style={{ flex: 1, textAlign: "left" }}
        onClick={() => navigate(`/chat?thread=${item.thread_id}`)}
      >
        <div>{item.title || "未命名"}</div>
        <div className="hint">
          {item.workspace} · {formatWhen(item.updated_at) || item.thread_id.slice(0, 8)}
        </div>
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
    </div>
  );
}

export default function SessionsPage() {
  const navigate = useNavigate();
  const threads = useHarness((s) => s.threads);
  const workspace = useHarness((s) => s.workspace);
  const connected = useHarness((s) => s.connected);
  const refreshThreads = useHarness((s) => s.refreshThreads);
  const startThread = useHarness((s) => s.startThread);

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
          <p>归档 = 从进行中藏起来，不删记录，CLI 也不会自动续上。恢复后重新出现。</p>
        </div>
        <button
          type="button"
          className="btn"
          disabled={!connected || !workspace}
          onClick={() => {
            void startThread().then((info) => navigate(`/chat?thread=${info.thread_id}`));
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
