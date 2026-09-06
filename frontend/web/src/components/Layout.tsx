import { useEffect } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useHarness } from "../store/session";
import SessionNav from "./SessionNav";

function ChatIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  );
}

function HistoryIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="1 4 1 10 7 10" />
      <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
    </svg>
  );
}

function SkillsIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden>
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

export default function Layout() {
  const navigate = useNavigate();
  const connected = useHarness((s) => s.connected);
  const connecting = useHarness((s) => s.connecting);
  const error = useHarness((s) => s.error);
  const workspace = useHarness((s) => s.workspace);
  const connect = useHarness((s) => s.connect);
  const newDraft = useHarness((s) => s.newDraft);

  useEffect(() => {
    void connect();
  }, [connect]);

  return (
    <div className="app">
      <nav className="nav">
        <div className="brand">
          <span className="logo">{"{}"}</span>
          <span>
            <div className="brand-name">
              Har<em>ness</em>
            </div>
            <div className="brand-sub">Local Agent</div>
          </span>
        </div>

        <button
          type="button"
          className="new-chat"
          disabled={!connected || !workspace}
          onClick={() => {
            newDraft();
            navigate("/chat");
          }}
        >
          <PlusIcon />
          新对话
        </button>

        <div className="group-label">工作台</div>
        <NavLink to="/chat">Chat</NavLink>
        <NavLink to="/sessions">Sessions</NavLink>
        <NavLink to="/skills">Skills</NavLink>
        <NavLink to="/settings">Settings</NavLink>

        <SessionNav />

        <div className={`status ${connected ? "ok" : "bad"}`}>
          <div className="status-row">
            <span className="status-dot" />
            {connecting ? (
              <span className="status-text">连接中…</span>
            ) : connected ? (
              <span className="status-text">已连接</span>
            ) : (
              <span className="status-text">未连接</span>
            )}
            <span className="status-server">App Server</span>
          </div>
          {!connected && !connecting ? (
            <button type="button" className="status-retry" onClick={() => void connect()}>
              重试连接
            </button>
          ) : null}
          {error ? <span className="hint">{error}</span> : null}
        </div>
      </nav>
      <div className="page">
        {error && connected ? <div className="banner">{error}</div> : null}
        <Outlet />
      </div>
    </div>
  );
}
