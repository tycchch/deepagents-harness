import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import ProviderSettings from "../components/ProviderSettings";
import { useHarness } from "../store/session";

export default function SettingsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const workspace = useHarness((s) => s.workspace);
  const config = useHarness((s) => s.config);
  const connected = useHarness((s) => s.connected);
  const setWorkspace = useHarness((s) => s.setWorkspace);
  const refreshConfig = useHarness((s) => s.refreshConfig);
  const setConfig = useHarness((s) => s.setConfig);
  const [localWs, setLocalWs] = useState(workspace);
  const [sandbox, setSandbox] = useState(Boolean((config.sandbox as { enabled?: boolean } | undefined)?.enabled));

  useEffect(() => {
    if (connected) void refreshConfig();
  }, [connected, refreshConfig]);

  useEffect(() => {
    setLocalWs(workspace);
    setSandbox(Boolean((config.sandbox as { enabled?: boolean } | undefined)?.enabled));
  }, [workspace, config]);

  return (
    <>
      <header>
        <div>
          <h1>Settings</h1>
          <p>workspace 是整棵项目目录。智能体工具只能走虚拟路径 /workspace/，对应下面填的本机路径。</p>
        </div>
        <div className="actions" style={{ marginTop: 0 }}>
        <button
          type="button"
          className="btn secondary"
          onClick={() => {
            if (location.key === "default") navigate("/chat");
            else navigate(-1);
          }}
        >
          返回
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => {
            void setWorkspace(localWs.trim());
            if (connected) {
              void setConfig({
                sandbox: { ...(typeof config.sandbox === "object" ? config.sandbox : {}), enabled: sandbox },
              });
            }
          }}
        >
          保存
        </button>
        </div>
      </header>
      <main>
        <div className="field">
          <label>workspace（整目录，不是单个文件）</label>
          <input value={localWs} onChange={(e) => setLocalWs(e.target.value)} placeholder="E:\workSpace\deepagentsSpace" />
          <p className="hint">
            保存后立刻套到当前会话。智能体请用 ls /workspace、读 /workspace/foo.py，不要传 E:\ 这种本机路径。
          </p>
        </div>
        <ProviderSettings />
        <label className="field">
          <span>sandbox</span>
          <input type="checkbox" checked={sandbox} onChange={(e) => setSandbox(e.target.checked)} />
        </label>
        <p className="hint">旧的 DEEPSEEK_* 仍可写在 backend/.env，首次启动会自动生成一条 DeepSeek 供应商。</p>
      </main>
    </>
  );
}
