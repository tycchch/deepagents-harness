import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AGENT_PERMISSIONS,
  useHarness,
  type AgentPermission,
  type AgentProfile,
} from "../store/session";

type Draft = {
  id: string;
  name: string;
  prompt: string;
  workspace: string;
  permission: AgentPermission;
};

const EMPTY_DRAFT: Draft = {
  id: "",
  name: "",
  prompt: "",
  workspace: "",
  permission: "confirm",
};

function toDraft(agent: AgentProfile): Draft {
  return {
    id: agent.id,
    name: agent.name,
    prompt: agent.prompt,
    workspace: agent.workspace,
    permission: agent.permission,
  };
}

export default function AgentsPage() {
  const navigate = useNavigate();
  const agents = useHarness((s) => s.agents);
  const activeAgentId = useHarness((s) => s.activeAgentId);
  const connected = useHarness((s) => s.connected);
  const currentWorkspace = useHarness((s) => s.workspace);
  const saveAgent = useHarness((s) => s.saveAgent);
  const deleteAgent = useHarness((s) => s.deleteAgent);
  const selectAgent = useHarness((s) => s.selectAgent);
  const setWorkspace = useHarness((s) => s.setWorkspace);
  const newDraft = useHarness((s) => s.newDraft);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const editing = Boolean(draft.id);

  useEffect(() => {
    if (!draft.workspace && currentWorkspace) {
      setDraft((prev) => ({ ...prev, workspace: prev.workspace || currentWorkspace }));
    }
  }, [currentWorkspace, draft.workspace]);

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function save() {
    const name = draft.name.trim();
    if (!name) return;
    saveAgent({
      id: draft.id || crypto.randomUUID(),
      name,
      prompt: draft.prompt,
      workspace: draft.workspace.trim(),
      permission: draft.permission,
    });
    setDraft(EMPTY_DRAFT);
  }

  async function start(agent: AgentProfile) {
    selectAgent(agent.id);
    if (agent.workspace) await setWorkspace(agent.workspace);
    newDraft();
    navigate("/chat");
  }

  const permissionText = (value: AgentPermission) =>
    AGENT_PERMISSIONS.find((item) => item.value === value)?.label ?? value;

  return (
    <>
      <header>
        <div>
          <h1>智能体</h1>
          <p>创建可复用的智能体档案，启动时自动应用自定义提示词、工作目录和权限约束。</p>
        </div>
        <div className="actions" style={{ marginTop: 0 }}>
          {editing ? (
            <button type="button" className="btn secondary" onClick={() => setDraft(EMPTY_DRAFT)}>
              取消编辑
            </button>
          ) : null}
          <button type="button" className="btn" onClick={save} disabled={!draft.name.trim()}>
            {editing ? "保存智能体" : "创建智能体"}
          </button>
        </div>
      </header>
      <main className="agents-main">
        <div className="agents-content">
          <div className="agents-grid">
            {agents.map((agent) => {
              const active = agent.id === activeAgentId;
              return (
                <article key={agent.id} className={`agent-card${active ? " active" : ""}`}>
                  <div className="agent-card-head">
                    <div>
                      <h2>{agent.name}</h2>
                      <p className="hint">{agent.workspace || "使用当前工作目录"}</p>
                    </div>
                    <span className={`agent-permission ${agent.permission}`}>{permissionText(agent.permission)}</span>
                  </div>
                  <p className="agent-prompt">{agent.prompt || "未填写自定义提示词"}</p>
                  <div className="agent-card-actions">
                    <button type="button" className="btn" disabled={!connected} onClick={() => void start(agent)}>
                      启动
                    </button>
                    <button type="button" className="btn secondary" onClick={() => setDraft(toDraft(agent))}>
                      编辑
                    </button>
                    <button
                      type="button"
                      className="btn danger secondary"
                      onClick={() => {
                        if (window.confirm(`删除智能体「${agent.name}」？`)) {
                          deleteAgent(agent.id);
                          if (draft.id === agent.id) setDraft(EMPTY_DRAFT);
                        }
                      }}
                    >
                      删除
                    </button>
                  </div>
                </article>
              );
            })}
            {!agents.length ? <p className="hint">还没有智能体。先在下面填写名称和提示词，创建一个。</p> : null}
          </div>

          <section className="settings-panel">
            <h2 className="section-title">{editing ? "编辑智能体" : "创建智能体"}</h2>
            <div className="field">
              <label htmlFor="agent-name">名称</label>
              <input
                id="agent-name"
                value={draft.name}
                onChange={(event) => update("name", event.target.value)}
                placeholder="例如：代码审查助手"
              />
            </div>
            <div className="field">
              <label htmlFor="agent-workspace">工作目录</label>
              <input
                id="agent-workspace"
                value={draft.workspace}
                onChange={(event) => update("workspace", event.target.value)}
                placeholder="E:\workspace\my-project"
              />
              <p className="hint">启动智能体时会自动切换到这个目录；对话中请使用 /workspace/ 虚拟路径。</p>
            </div>
            <div className="field permission-field">
              <span className="field-label">权限</span>
              <div className="permission-options" role="radiogroup" aria-label="权限">
                {AGENT_PERMISSIONS.map((item) => {
                  const selected = draft.permission === item.value;
                  return (
                    <button
                      key={item.value}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      className={`permission-card${selected ? " active" : ""}`}
                      onClick={() => update("permission", item.value)}
                    >
                      <strong>{item.label}</strong>
                      <small>{item.description}</small>
                      <span className={`permission-dot${selected ? " on" : ""}`} aria-hidden />
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="field">
              <label htmlFor="agent-prompt">自定义提示词</label>
              <textarea
                id="agent-prompt"
                rows={8}
                value={draft.prompt}
                onChange={(event) => update("prompt", event.target.value)}
                placeholder="描述这个智能体的角色、目标、工作方式和输出格式。"
              />
            </div>
          </section>
        </div>
      </main>
    </>
  );
}
