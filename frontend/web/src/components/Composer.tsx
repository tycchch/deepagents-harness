import { useState } from "react";

type Props = {
  busy: boolean;
  disabled?: boolean;
  onSend: (text: string) => void;
  onInterrupt: () => void;
};

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
      <textarea
        value={text}
        disabled={disabled}
        placeholder={disabled ? "先在 Settings 填写 workspace" : "输入，Enter 发送，Shift+Enter 换行"}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
      />
      {busy ? (
        <button type="button" className="btn danger" onClick={onInterrupt}>
          中断
        </button>
      ) : (
        <button type="button" className="btn" disabled={disabled || !text.trim()} onClick={submit}>
          发送
        </button>
      )}
    </div>
  );
}
