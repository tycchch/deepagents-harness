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
  if (pending) return seconds > 0 ? `思考中 · ${seconds.toFixed(1)}s` : "思考中";
  if (seconds > 0) return `已思考（用时 ${Math.max(1, Math.round(seconds))} 秒）`;
  return "已思考";
}

export default function ThoughtProcess({ items }: { items: ChatItem[] }) {
  const pending = items.some((item) => item.pending);
  const [open, setOpen] = useState(true);
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
    <div className={`thought${open ? " open" : ""}`}>
      <button type="button" className="thought-head" onClick={() => setOpen(!open)}>
        <span className="thought-mark" aria-hidden>
          ◇
        </span>
        <span>{title(pending, seconds)}</span>
        <span className="thought-caret">{open ? "▾" : "▸"}</span>
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
