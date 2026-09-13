import { useState } from "react";
import { Send, Square } from "lucide-react";
import { useHarness } from "../store/session";

type Props = {
  busy: boolean;
  disabled?: boolean;
  onSend: (text: string) => void;
  onInterrupt: () => void;
};

export default function Composer({ busy, disabled, onSend, onInterrupt }: Props) {
  const [text, setText] = useState("");
  const models = useHarness((s) => s.models);
  const setModel = useHarness((s) => s.setModel);
  const current = `${models.active_provider}::${models.active_model}`;

  function submit() {
    const next = text.trim();
    if (!next || busy || disabled) return;
    onSend(next);
    setText("");
  }

  return (
    <div className="composer">
      <div className="composer-inner">
        <textarea
          value={text}
          disabled={disabled}
          placeholder={disabled ? "先在设置中填写工作目录" : "描述任务，或直接提问…"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        {models.providers.length ? (
          <select
            className="model-pick"
            disabled={disabled || busy}
            value={current}
            title="切换模型，等同 CLI /model"
            onChange={(e) => {
              const [providerId, model] = e.target.value.split("::");
              if (model) void setModel(model, providerId);
            }}
          >
            {models.providers.map((provider) => (
              <optgroup key={provider.id} label={`${provider.name} · ${provider.protocol}`}>
                {(provider.models || []).map((item) => (
                  <option key={`${provider.id}-${item.id}`} value={`${provider.id}::${item.id}`}>
                    {item.label || item.id}
                  </option>
                ))}
                {Object.entries(provider.mapping || {}).map(([alias, id]) =>
                  alias === id ? null : (
                    <option key={`${provider.id}-${alias}`} value={`${provider.id}::${alias}`}>
                      {alias} → {id}
                    </option>
                  ),
                )}
              </optgroup>
            ))}
          </select>
        ) : null}
        {busy ? (
          <button
            type="button"
            className="round-btn danger"
            title="中断当前任务"
            aria-label="中断"
            onClick={onInterrupt}
          >
            <Square size="15" aria-hidden />
          </button>
        ) : (
          <button
            type="button"
            className="round-btn"
            disabled={disabled || !text.trim()}
            title="发送 (Enter)"
            aria-label="发送"
            onClick={submit}
          >
            <Send size={17} aria-hidden />
          </button>
        )}
      </div>
    </div>
  );
}
