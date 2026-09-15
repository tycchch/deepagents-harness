import { useEffect, useRef, useState } from "react";
import type { ChatItem } from "../store/session";

function toolLabel(item: ChatItem): string {
  const name = item.tool || item.type;
  const detail = item.path || (item.text || "").replace(/\s+/g, " ").trim();
  if (!detail) return name;
  return detail.length > 72 ? `${name}  ${detail.slice(0, 69)}…` : `${name}  ${detail}`;
}

function Step({ item }: { item: ChatItem }) {
  if (item.type === "reasoning") {
    const text = (item.text || "").trim();
    if (!text) return null;
    return <p className="step-think">{text}</p>;
  }

  const lines = (item.text || "").split("\n");
  const looksDiff = item.type === "file_change" && lines.some((line) => line.startsWith("+") || line.startsWith("-"));
  const body = item.text || item.path;
  return (
    <details className="step-tool" open={item.pending && Boolean(body)}>
      <summary>
        <span className={`dot${item.pending ? " spin" : ""}`} />
        {toolLabel(item)}
        {item.pending ? " …" : ""}
      </summary>
      {looksDiff ? (
        <pre className="diff">
          {lines.map((line, i) => (
            <div key={i} className={line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : ""}>
              {line || " "}
            </div>
          ))}
        </pre>
      ) : body ? (
        <pre>{item.text || item.path}</pre>
      ) : null}
    </details>
  );
}

function title(pending: boolean, seconds: number): string {
  const used = Math.max(1, Math.round(seconds));
  if (pending) return seconds > 0 ? `思考中(用时${used}秒)` : "思考中";
  if (seconds > 0) return `已思考(用时${used}秒)`;
  return "已思考";
}

function ThoughtMark() {
  return (
    <svg className="thought-logo" viewBox="0 0 24 24" aria-hidden>
      <path
        d="M7.2 12c0-2.4 1.8-4.2 4.2-4.2 1.4 0 2.4.6 3.2 1.5L16 7.8C14.9 6.5 13.4 5.6 11.4 5.6 7.8 5.6 5 8.3 5 12s2.8 6.4 6.4 6.4c2 0 3.5-.9 4.6-2.2L14.6 14.7c-.8.9-1.8 1.5-3.2 1.5-2.4 0-4.2-1.8-4.2-4.2Zm9.6 0c0 2.4-1.8 4.2-4.2 4.2-1.4 0-2.4-.6-3.2-1.5L8 16.2c1.1 1.3 2.6 2.2 4.6 2.2 3.6 0 6.4-2.7 6.4-6.4S16.2 5.6 12.6 5.6c-2 0-3.5.9-4.6 2.2L9.4 9.3c.8-.9 1.8-1.5 3.2-1.5 2.4 0 4.2 1.8 4.2 4.2Z"
        fill="currentColor"
      />
    </svg>
  );
}

export default function ThoughtProcess({ items }: { items: ChatItem[] }) {
  const pending = items.some((item) => item.pending);
  const [open, setOpen] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const started = useRef<number | null>(null);

  useEffect(() => {
    if (pending) {
      started.current ??= Date.now();
      const tick = () => setSeconds((Date.now() - (started.current ?? Date.now())) / 1000);
      tick();
      const id = window.setInterval(tick, 200);
      return () => window.clearInterval(id);
    }
    if (started.current) setSeconds((Date.now() - started.current) / 1000);
  }, [pending]);

  useEffect(() => {
    if (pending) setOpen(true);
  }, [pending]);

  return (
    <div className={`thought${open ? " open" : ""}${pending ? " pending" : ""}`}>
      <button type="button" className="thought-head" onClick={() => setOpen(!open)}>
        <ThoughtMark />
        <span>{title(pending, seconds)}</span>
        <span className="thought-caret" aria-hidden>
          ›
        </span>
      </button>
      {open ? (
        <div className="thought-body">
          {items.map((item) => (
            <Step key={item.item_id} item={item} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
