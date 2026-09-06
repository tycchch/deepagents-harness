import { useState, type ReactNode } from "react";

type Segment = { kind: "text" | "code"; lang: string; body: string };

const FENCE = /```([^\n`]*)\n?([\s\S]*?)(?:```|$)/g;
const INLINE_CODE = /`([^`\n]+)`/g;

function splitMarkdown(source: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  FENCE.lastIndex = 0;
  let match = FENCE.exec(source);
  while (match) {
    if (match.index > last) out.push({ kind: "text", lang: "", body: source.slice(last, match.index) });
    out.push({ kind: "code", lang: match[1].trim(), body: match[2] });
    last = FENCE.lastIndex;
    match = FENCE.exec(source);
  }
  if (last < source.length) out.push({ kind: "text", lang: "", body: source.slice(last) });
  return out;
}

function CodeBlock({ lang, body }: { lang: string; body: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(body);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <figure className="code">
      <figcaption>
        <span>{lang || "code"}</span>
        <button type="button" onClick={() => void copy()}>
          {copied ? "已复制" : "复制"}
        </button>
      </figcaption>
      <pre>
        <code>{body}</code>
      </pre>
    </figure>
  );
}

function InlineText({ body }: { body: string }) {
  const nodes: ReactNode[] = [];
  let last = 0;
  INLINE_CODE.lastIndex = 0;
  let match = INLINE_CODE.exec(body);
  while (match) {
    if (match.index > last) nodes.push(body.slice(last, match.index));
    nodes.push(<code key={`${match.index}-code`}>{match[1]}</code>);
    last = INLINE_CODE.lastIndex;
    match = INLINE_CODE.exec(body);
  }
  if (last < body.length) nodes.push(body.slice(last));
  return <p className="prose">{nodes}</p>;
}

export default function Markdown({ text }: { text: string }) {
  if (!text) return null;
  return (
    <>
      {splitMarkdown(text).map((segment, index) =>
        segment.kind === "code" ? (
          <CodeBlock key={index} lang={segment.lang} body={segment.body} />
        ) : segment.body.trim() ? (
          <InlineText key={index} body={segment.body.replace(/^\n+|\n+$/g, "")} />
        ) : null,
      )}
    </>
  );
}
