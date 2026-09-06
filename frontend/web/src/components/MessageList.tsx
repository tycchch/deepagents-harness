import { useEffect, useRef } from "react";
import type { ChatItem } from "../store/session";
import Markdown from "./Markdown";
import ThoughtProcess from "./ThoughtProcess";

function isProcess(item: ChatItem): boolean {
  return (
    item.type === "reasoning" ||
    item.type === "tool_call" ||
    item.type === "command_execution" ||
    item.type === "skill_use" ||
    item.type === "file_change"
  );
}

type Block =
  | { kind: "user"; item: ChatItem }
  | { kind: "turn"; process: ChatItem[]; answers: ChatItem[] };

function groupTurns(items: ChatItem[]): Block[] {
  const blocks: Block[] = [];
  let process: ChatItem[] = [];
  let answers: ChatItem[] = [];

  function flush() {
    if (!process.length && !answers.length) return;
    blocks.push({ kind: "turn", process, answers });
    process = [];
    answers = [];
  }

  for (const item of items) {
    if (item.type === "user_message") {
      flush();
      blocks.push({ kind: "user", item });
      continue;
    }
    if (isProcess(item)) process.push(item);
    else answers.push(item);
  }
  flush();
  return blocks;
}

export default function MessageList({ items }: { items: ChatItem[] }) {
  const anchor = useRef<HTMLDivElement>(null);
  const seen = useRef(0);

  useEffect(() => {
    const scroller = anchor.current?.closest("main");
    if (!scroller) return;
    const gap = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    const firstPaint = seen.current === 0 && items.length > 0;
    seen.current = items.length;
    if (firstPaint || gap < 160) scroller.scrollTop = scroller.scrollHeight;
  }, [items]);

  if (!items.length) return <p className="hint">发一条消息开始。只走 App Server，前端不跑 agent。</p>;

  return (
    <div className="messages">
      {groupTurns(items).map((block, index) => {
        if (block.kind === "user") {
          return (
            <div key={block.item.item_id} className="msg user">
              {block.item.text}
            </div>
          );
        }
        return (
          <div key={`turn-${index}`} className="turn">
            {block.process.length ? <ThoughtProcess items={block.process} /> : null}
            {block.answers.map((item) => (
              <div key={item.item_id} className={`msg agent${item.pending ? " pending" : ""}`}>
                {item.text ? <Markdown text={item.text} /> : item.pending ? <span className="dots">…</span> : null}
              </div>
            ))}
          </div>
        );
      })}
      <div ref={anchor} />
    </div>
  );
}
