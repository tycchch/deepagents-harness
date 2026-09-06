import type { ChatItem } from "../store/session";

export default function Reasoning({ item }: { item: ChatItem }) {
  const text = (item.text || "").trim();
  if (!text) return null;
  return (
    <details className="thinking" open={item.pending}>
      <summary>思考过程{item.pending ? " …" : ""}</summary>
      <div>{text}</div>
    </details>
  );
}
