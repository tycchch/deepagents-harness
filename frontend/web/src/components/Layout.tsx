import { useEffect } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Bot, History, MessageSquare, Plus, Settings, Wrench } from "lucide-react";
import { useHarness } from "../store/session";
import SessionNav from "./SessionNav";

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
            <div className="brand-sub">本地智能体</div>
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
          <Plus size={17} aria-hidden />
          新对话
        </button>

        <div className="group-label">工作台</div>
        <NavLink to="/chat" aria-label="对话" title="对话">
          <MessageSquare size={17} aria-hidden />
          <span>对话</span>
        </NavLink>
        <NavLink to="/agents" aria-label="智能体" title="智能体">
          <Bot size={17} aria-hidden />
          <span>智能体</span>
        </NavLink>
        <NavLink to="/sessions" aria-label="会话" title="会话">
          <History size={17} aria-hidden />
          <span>会话</span>
        </NavLink>
        <NavLink to="/skills" aria-label="技能" title="技能">
          <Wrench size={17} aria-hidden />
          <span>技能</span>
        </NavLink>
        <NavLink to="/settings" aria-label="设置" title="设置">
          <Settings size={17} aria-hidden />
          <span>设置</span>
        </NavLink>

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
            <span className="status-server">应用服务</span>
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
