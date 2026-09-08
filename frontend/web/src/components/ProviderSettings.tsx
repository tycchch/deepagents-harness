import { useEffect, useState } from "react";
import type { ProviderInfo } from "../protocol/types";
import { useHarness } from "../store/session";

type Draft = {
  id: string;
  name: string;
  protocol: "anthropic" | "openai";
  base_url: string;
  api_key: string;
  models: string;
  haiku: string;
  sonnet: string;
  opus: string;
};

const EMPTY: Draft = {
  id: "",
  name: "",
  protocol: "openai",
  base_url: "",
  api_key: "",
  models: "",
  haiku: "",
  sonnet: "",
  opus: "",
};

const PRESETS: { label: string; patch: Partial<Draft> }[] = [
  {
    label: "Anthropic 原生",
    patch: { protocol: "anthropic", base_url: "https://api.anthropic.com", models: "claude-sonnet-4-5,claude-opus-4-6,claude-haiku-4-5" },
  },
  {
    label: "OpenAI 兼容",
    patch: { protocol: "openai", base_url: "https://api.openai.com/v1", models: "gpt-4.1,gpt-4.1-mini" },
  },
  {
    label: "DeepSeek OpenAI",
    patch: { protocol: "openai", base_url: "https://api.deepseek.com", models: "deepseek-chat,deepseek-reasoner" },
  },
  {
    label: "DeepSeek Anthropic",
    patch: { protocol: "anthropic", base_url: "https://api.deepseek.com/anthropic", models: "deepseek-chat,deepseek-reasoner" },
  },
];

function toDraft(item: ProviderInfo): Draft {
  return {
    id: item.id,
    name: item.name,
    protocol: item.protocol === "anthropic" ? "anthropic" : "openai",
    base_url: item.base_url,
    api_key: item.has_key ? "***" : "",
    models: (item.models || []).map((m) => (m.label && m.label !== m.id ? `${m.id}|${m.label}` : m.id)).join(", "),
    haiku: item.mapping?.haiku || "",
    sonnet: item.mapping?.sonnet || "",
    opus: item.mapping?.opus || "",
  };
}

export default function ProviderSettings() {
  const connected = useHarness((s) => s.connected);
  const models = useHarness((s) => s.models);
  const refreshModels = useHarness((s) => s.refreshModels);
  const upsertProvider = useHarness((s) => s.upsertProvider);
  const deleteProvider = useHarness((s) => s.deleteProvider);
  const setModel = useHarness((s) => s.setModel);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const editing = Boolean(draft.id);

  useEffect(() => {
    if (connected) void refreshModels();
  }, [connected, refreshModels]);

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function save() {
    const name = draft.name.trim();
    if (!name) return;
    const mapping: Record<string, string> = {};
    if (draft.haiku.trim()) mapping.haiku = draft.haiku.trim();
    if (draft.sonnet.trim()) mapping.sonnet = draft.sonnet.trim();
    if (draft.opus.trim()) mapping.opus = draft.opus.trim();
    void upsertProvider({
      id: draft.id,
      name,
      protocol: draft.protocol,
      base_url: draft.base_url.trim(),
      api_key: draft.api_key,
      models: draft.models,
      mapping,
    }).then(() => setDraft(EMPTY));
  }

  return (
    <section className="providers">
      <h2 className="section-title">模型供应商</h2>
      <p className="hint">
        类似 cc-switch：选协议、填 API Key / Base URL，再用 haiku / sonnet / opus 映射到真实模型名。
        密钥只存在本机 App Server（~/.harness/providers.json），前端只显示 ***。
      </p>
      <div className="provider-list">
        {models.providers.map((item) => {
          const on = item.id === models.active_provider;
          return (
            <div key={item.id} className={`provider-card${on ? " active" : ""}`}>
              <div>
                <strong>{item.name}</strong>
                <div className="hint">
                  {item.protocol === "anthropic" ? "Anthropic 原生" : "OpenAI 兼容"} · {item.base_url || "默认端点"}
                  {item.has_key ? " · 已配置 key" : " · 无 key"}
                </div>
              </div>
              <div className="actions" style={{ marginTop: 0 }}>
                <button type="button" className="btn secondary" onClick={() => setDraft(toDraft(item))}>
                  编辑
                </button>
                <button
                  type="button"
                  className="btn secondary"
                  disabled={!item.models?.length}
                  onClick={() => void setModel(item.models[0].id, item.id)}
                >
                  {on ? "使用中" : "启用"}
                </button>
                <button
                  type="button"
                  className="btn danger"
                  onClick={() => {
                    if (window.confirm(`删除供应商「${item.name}」？`)) void deleteProvider(item.id);
                  }}
                >
                  删除
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <h2 className="section-title">{editing ? "编辑供应商" : "新增供应商"}</h2>
      <div className="preset-row">
        {PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            className="btn secondary"
            onClick={() => setDraft((prev) => ({ ...prev, ...preset.patch }))}
          >
            {preset.label}
          </button>
        ))}
      </div>
      <div className="field">
        <label>名称</label>
        <input value={draft.name} onChange={(e) => update("name", e.target.value)} placeholder="DeepSeek / Claude / OpenRouter" />
      </div>
      <div className="field">
        <label>协议</label>
        <select value={draft.protocol} onChange={(e) => update("protocol", e.target.value as Draft["protocol"])}>
          <option value="anthropic">Anthropic 原生（Messages）</option>
          <option value="openai">OpenAI 兼容</option>
        </select>
      </div>
      <div className="field">
        <label>Base URL</label>
        <input
          value={draft.base_url}
          onChange={(e) => update("base_url", e.target.value)}
          placeholder={draft.protocol === "anthropic" ? "https://api.anthropic.com 或 …/anthropic" : "https://api.deepseek.com"}
        />
      </div>
      <div className="field">
        <label>API Key</label>
        <input
          type="password"
          value={draft.api_key}
          onChange={(e) => update("api_key", e.target.value)}
          placeholder={editing ? "留 *** 表示不改" : "sk-…"}
        />
      </div>
      <div className="field">
        <label>模型列表（逗号分隔，可用 id|显示名）</label>
        <input
          value={draft.models}
          onChange={(e) => update("models", e.target.value)}
          placeholder="deepseek-chat, deepseek-reasoner|Reasoner"
        />
      </div>
      <div className="map-grid">
        <div className="field">
          <label>映射 haiku</label>
          <input value={draft.haiku} onChange={(e) => update("haiku", e.target.value)} placeholder="快模型 id" />
        </div>
        <div className="field">
          <label>映射 sonnet</label>
          <input value={draft.sonnet} onChange={(e) => update("sonnet", e.target.value)} placeholder="日常模型 id" />
        </div>
        <div className="field">
          <label>映射 opus</label>
          <input value={draft.opus} onChange={(e) => update("opus", e.target.value)} placeholder="强模型 id" />
        </div>
      </div>
      <div className="actions">
        {editing ? (
          <button type="button" className="btn secondary" onClick={() => setDraft(EMPTY)}>
            取消
          </button>
        ) : null}
        <button type="button" className="btn" disabled={!draft.name.trim() || !connected} onClick={save}>
          {editing ? "保存供应商" : "添加供应商"}
        </button>
      </div>
    </section>
  );
}
