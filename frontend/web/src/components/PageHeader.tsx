import { useLocation } from "react-router-dom";
import { useHarness } from "../store/session";

const TITLES: Record<string, string> = {
  "/chat": "对话",
  "/agents": "智能体",
  "/sessions": "会话",
  "/skills": "技能",
  "/settings": "设置",
};

function threadTitle(title: string | undefined, fallback: string): string {
  const next = title?.trim();
  return next || fallback;
}

export default function PageHeader() {
  const location = useLocation();
  const thread = useHarness((s) => s.thread);
  const workspace = useHarness((s) => s.workspace);
  const activeAgent = useHarness((s) => s.agents.find((item) => item.id === s.activeAgentId));
  const base = `/${location.pathname.split("/").filter(Boolean)[0] || "chat"}`;
  const onChat = base === "/chat";
  const title = onChat ? threadTitle(thread?.title, "新对话") : TITLES[base] || "Harness";
  const workspaceLabel = thread?.workspace || workspace;

  return (
    <header className="chrome-header">
      <h1 title={title}>{title}</h1>
      <div className="chrome-meta">
        {onChat && activeAgent ? (
          <span className="badge brand" title={activeAgent.prompt}>
            {activeAgent.name}
          </span>
        ) : null}
        {onChat && workspaceLabel ? (
          <span className="badge" title={workspaceLabel}>
            {workspaceLabel}
          </span>
        ) : null}
        {onChat && !workspaceLabel ? <span className="badge bad">未设置工作目录</span> : null}
      </div>
    </header>
  );
}
