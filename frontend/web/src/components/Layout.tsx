import { useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useHarness } from "../store/session";
import SessionNav from "./SessionNav";

export default function Layout() {
  const connected = useHarness((s) => s.connected);
  const connecting = useHarness((s) => s.connecting);
  const error = useHarness((s) => s.error);
  const connect = useHarness((s) => s.connect);

  useEffect(() => {
    void connect();
  }, [connect]);

  return (
    <div className="app">
      <nav className="nav">
        <div className="brand">HARNESS</div>
        <NavLink to="/chat">Chat</NavLink>
        <NavLink to="/skills">Skills</NavLink>
        <NavLink to="/settings">Settings</NavLink>
        <SessionNav />
        <div className={`status ${connected ? "ok" : "bad"}`}>
          {connecting ? "连接中…" : connected ? "已连接 App Server" : "未连接"}
          {!connected && !connecting ? (
            <>
              <br />
              <button type="button" className="btn secondary" onClick={() => void connect()}>
                重连
              </button>
            </>
          ) : null}
        </div>
      </nav>
      <div className="page">
        {error ? <div className="banner">{error}</div> : null}
        <Outlet />
      </div>
    </div>
  );
}
