import { useEffect, useRef } from "react";
import type { ChatItem } from "../store/session";
import Markdown from "./Markdown";
import ThoughtProcess from "./ThoughtProcess";

type Props = {
  items: ChatItem[];
  canSuggest?: boolean;
  onSuggest?: (text: string) => void;
};

const SUGGESTIONS = [
  { icon: "spark", label: "用一句话介绍这个项目" },
  { icon: "lens", label: "检查代码里有什么问题" },
  { icon: "pencil", label: "列出值得改进的地方" },
];

function SparkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z" />
    </svg>
  );
}
function LensIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.5" y2="16.5" />
    </svg>
  );
}
function PencilIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
    </svg>
  );
}

function suggestIcon(icon: string) {
  if (icon === "spark") return <SparkIcon />;
  if (icon === "pencil") return <PencilIcon />;
  return <LensIcon />;
}

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

export default function MessageList({ items, canSuggest = false, onSuggest }: Props) {
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

  if (!items.length) {
    return (
      <div className="welcome">
        <div className="welcome-orb">{"{}"}</div>
        <h1>
          你好，我是 <span className="accent-text">Harness</span>
        </h1>
        <p>
          本地编程智能体。可以读代码、改文件、跑命令、查资料。
          描述任务即可，过程会显示在对话里。
        </p>
        <div className="suggests">
          {SUGGESTIONS.map((s) => (
            <button
              key={s.label}
              type="button"
              className="suggest"
              disabled={!canSuggest}
              onClick={() => onSuggest?.(s.label)}
            >
              {suggestIcon(s.icon)}
              {s.label}
            </button>
          ))}
        </div>
        <p className="footnote">本地运行 · 数据只经过你的 App Server · Enter 发送，Shift+Enter 换行</p>
      </div>
    );
  }

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
