import { useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";

type Segment = { kind: "text" | "code"; lang: string; body: string };

const FENCE = /```([^\n`]*)\n?([\s\S]*?)(?:```|$)/g;

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

function MarkdownText({ body }: { body: string }) {
  const html = marked.parse(body, { gfm: true, breaks: true, async: false }) as string;
  const safe = DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["style"],
    FORBID_ATTR: ["style"],
  });
  return <div className="prose" dangerouslySetInnerHTML={{ __html: safe }} />;
}

export default function Markdown({ text }: { text: string }) {
  if (!text) return null;
  return (
    <>
      {splitMarkdown(text).map((segment, index) =>
        segment.kind === "code" ? (
          <CodeBlock key={index} lang={segment.lang} body={segment.body} />
        ) : segment.body.trim() ? (
          <MarkdownText key={index} body={segment.body.replace(/^\n+|\n+$/g, "")} />
        ) : null,
      )}
    </>
  );
}
