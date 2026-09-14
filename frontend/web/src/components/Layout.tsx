import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Bot, ChevronLeft, ChevronRight, History, MessageSquare, PanelLeft, PanelLeftClose, Plus, Settings, Wrench } from "lucide-react";
import { useAppHistory } from "../hooks/useAppHistory";
import { useHarness } from "../store/session";
import PageHeader from "./PageHeader";
import SessionNav from "./SessionNav";

const NAV_KEY = "harness.navCollapsed";

export default function Layout() {
  const navigate = useNavigate();
  const history = useAppHistory();
  const connected = useHarness((s) => s.connected);
  const connecting = useHarness((s) => s.connecting);
  const error = useHarness((s) => s.error);
  const workspace = useHarness((s) => s.workspace);
  const connect = useHarness((s) => s.connect);
  const newDraft = useHarness((s) => s.newDraft);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(NAV_KEY) === "1");

  useEffect(() => {
    void connect();
  }, [connect]);

  function toggleNav() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(NAV_KEY, next ? "1" : "0");
      return next;
    });
  }

  return (
    <div className={`app${collapsed ? " nav-collapsed" : ""}`}>
      <nav className="nav">
        <div className="nav-chrome">
          <button
            type="button"
            className="nav-tool nav-fold"
            title={collapsed ? "展开侧栏" : "折叠侧栏"}
            aria-expanded={!collapsed}
            onClick={toggleNav}
          >
            {collapsed ? <PanelLeft size={15} aria-hidden /> : <PanelLeftClose size={15} aria-hidden />}
          </button>
          <button type="button" className="nav-tool" title="后退" disabled={!history.canBack} onClick={history.back}>
            <ChevronLeft size={16} aria-hidden />
          </button>
          <button
            type="button"
            className="nav-tool"
            title="前进"
            disabled={!history.canForward}
            onClick={history.forward}
          >
            <ChevronRight size={16} aria-hidden />
          </button>
        </div>

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
          <Plus size={15} aria-hidden />
          <span className="label">新对话</span>
        </button>

        <div className="group-label">工作台</div>
        <NavLink to="/chat" aria-label="对话" title="对话">
          <MessageSquare size={15} aria-hidden />
          <span>对话</span>
        </NavLink>
        <NavLink to="/agents" aria-label="智能体" title="智能体">
          <Bot size={15} aria-hidden />
          <span>智能体</span>
        </NavLink>
        <NavLink to="/sessions" aria-label="会话" title="会话">
          <History size={15} aria-hidden />
          <span>会话</span>
        </NavLink>
        <NavLink to="/skills" aria-label="技能" title="技能">
          <Wrench size={15} aria-hidden />
          <span>技能</span>
        </NavLink>
        <NavLink to="/settings" aria-label="设置" title="设置">
          <Settings size={15} aria-hidden />
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
        <PageHeader />
        {error && connected ? <div className="banner">{error}</div> : null}
        <Outlet />
      </div>
    </div>
  );
}
