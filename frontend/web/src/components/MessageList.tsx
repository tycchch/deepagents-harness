import type { ChatItem } from "../store/session";
import DiffView from "./DiffView";
import ToolCard from "./ToolCard";

export default function MessageList({ items }: { items: ChatItem[] }) {
  if (!items.length) return <p className="hint">发一条消息开始。只走 App Server，前端不跑 agent。</p>;
  return (
    <div className="messages">
      {items.map((item) => {
        if (item.type === "user_message") {
          return (
            <div key={item.item_id} className="bubble user">
              {item.text}
            </div>
          );
        }
        if (item.type === "file_change") {
          return <DiffView key={item.item_id} item={item} />;
        }
        if (item.type === "tool_call" || item.type === "command_execution" || item.type === "skill_use") {
          return <ToolCard key={item.item_id} item={item} />;
        }
        return (
          <div key={item.item_id} className={`bubble agent${item.pending ? " pending" : ""}`}>
            {item.text || (item.pending ? "…" : "")}
          </div>
        );
      })}
    </div>
  );
}
