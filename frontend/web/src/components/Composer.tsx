import { useState } from "react";

type Props = {
  busy: boolean;
  disabled?: boolean;
  onSend: (text: string) => void;
  onInterrupt: () => void;
};

function SendIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 19V5" />
      <path d="M5 12l7-7 7 7" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <rect x="5" y="5" width="14" height="14" rx="2.5" />
    </svg>
  );
}

export default function Composer({ busy, disabled, onSend, onInterrupt }: Props) {
  const [text, setText] = useState("");

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
          placeholder={disabled ? "先在 Settings 填写 workspace" : "描述任务，或直接提问…"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        {busy ? (
          <button
            type="button"
            className="round-btn danger"
            title="中断当前任务"
            aria-label="中断"
            onClick={onInterrupt}
          >
            <StopIcon />
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
            <SendIcon />
          </button>
        )}
      </div>
    </div>
  );
}
