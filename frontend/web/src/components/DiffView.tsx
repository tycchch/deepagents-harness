import type { ChatItem } from "../store/session";

export default function DiffView({ item }: { item: ChatItem }) {
  const lines = (item.text || "").split("\n");
  const looksDiff = lines.some((line) => line.startsWith("+") || line.startsWith("-"));
  return (
    <div className="card">
      <summary style={{ display: "block", cursor: "default" }}>{item.path || "file_change"}</summary>
      {looksDiff ? (
        <pre className="diff">
          {lines.map((line, i) => (
            <div key={i} className={line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : ""}>
              {line || " "}
            </div>
          ))}
        </pre>
      ) : item.text ? (
        <pre>{item.text}</pre>
      ) : null}
    </div>
  );
}
