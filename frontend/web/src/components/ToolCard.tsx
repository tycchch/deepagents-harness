import type { ChatItem } from "../store/session";

export default function ToolCard({ item }: { item: ChatItem }) {
  const title = item.tool || item.type;
  return (
    <details className="card" open={item.pending}>
      <summary>
        {title}
        {item.pending ? " …" : ""}
      </summary>
      {item.text ? <pre>{item.text}</pre> : null}
    </details>
  );
}
