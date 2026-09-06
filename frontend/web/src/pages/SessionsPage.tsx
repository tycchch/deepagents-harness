import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useHarness } from "../store/session";

export default function SessionsPage() {
  const navigate = useNavigate();
  const threads = useHarness((s) => s.threads);
  const workspace = useHarness((s) => s.workspace);
  const connected = useHarness((s) => s.connected);
  const refreshThreads = useHarness((s) => s.refreshThreads);
  const startThread = useHarness((s) => s.startThread);
  const archiveThread = useHarness((s) => s.archiveThread);

  useEffect(() => {
    if (connected) void refreshThreads();
  }, [connected, refreshThreads]);

  return (
    <>
      <header>
        <div>
          <h1>Sessions</h1>
          <p>thread/list · start · resume · archive</p>
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
        {!threads.length ? <p className="hint">还没有会话。</p> : null}
        {threads.map((item) => (
          <div key={item.thread_id} className="row">
            <button
              type="button"
              className="btn secondary"
              style={{ flex: 1, textAlign: "left" }}
              onClick={() => navigate(`/chat?thread=${item.thread_id}`)}
            >
              <div>{item.title || "未命名"}</div>
              <div className="hint">
                {item.workspace} · {item.updated_at || item.thread_id}
              </div>
            </button>
            <button type="button" className="btn secondary" onClick={() => void archiveThread(item.thread_id)}>
              归档
            </button>
          </div>
        ))}
      </main>
    </>
  );
}
