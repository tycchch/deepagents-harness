import { useEffect, useRef } from "react";
import type { ChatItem } from "../store/session";
import DiffView from "./DiffView";
import Markdown from "./Markdown";
import Reasoning from "./Reasoning";
import ToolCard from "./ToolCard";

export default function MessageList({ items }: { items: ChatItem[] }) {
  const anchor = useRef<HTMLDivElement>(null);
  const seen = useRef(0);

  useEffect(() => {
    const scroller = anchor.current?.closest("main");
    if (!scroller) return;
    // Stick to the bottom while streaming, but leave the user alone if they scrolled up to read.
    const gap = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    const firstPaint = seen.current === 0 && items.length > 0;
    seen.current = items.length;
    if (firstPaint || gap < 160) scroller.scrollTop = scroller.scrollHeight;
  }, [items]);

  if (!items.length) return <p className="hint">发一条消息开始。只走 App Server，前端不跑 agent。</p>;

  return (
    <div className="messages">
      {items.map((item) => {
        if (item.type === "user_message") {
          return (
            <div key={item.item_id} className="msg user">
              {item.text}
            </div>
          );
        }
        if (item.type === "reasoning") {
          return <Reasoning key={item.item_id} item={item} />;
        }
        if (item.type === "file_change") {
          return <DiffView key={item.item_id} item={item} />;
        }
        if (item.type === "tool_call" || item.type === "command_execution" || item.type === "skill_use") {
          return <ToolCard key={item.item_id} item={item} />;
        }
        return (
          <div key={item.item_id} className={`msg agent${item.pending ? " pending" : ""}`}>
            {item.text ? <Markdown text={item.text} /> : item.pending ? <span className="dots">…</span> : null}
          </div>
        );
      })}
      <div ref={anchor} />
    </div>
  );
}
