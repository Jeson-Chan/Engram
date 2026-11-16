/** 极简 Markdown 渲染（标题/粗体/代码/行内代码/列表/段落）——零依赖。 */

import { type ReactNode } from "react";

function renderInline(text: string, keyBase: string): ReactNode[] {
  const parts: ReactNode[] = [];
  // 依次匹配 `code`、**bold**、*italic*
  const regex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const token = m[0];
    if (token.startsWith("`")) {
      parts.push(<code key={`${keyBase}-c${i}`}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**")) {
      parts.push(<strong key={`${keyBase}-b${i}`}>{token.slice(2, -2)}</strong>);
    } else {
      parts.push(<em key={`${keyBase}-i${i}`}>{token.slice(1, -1)}</em>);
    }
    last = m.index + token.length;
    i += 1;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function Markdown({ text }: { text: string }) {
  const lines = (text || "").split("\n");
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  let code: string[] = [];
  let inCode = false;

  const flushList = () => {
    if (list.length > 0) {
      blocks.push(
        <ul key={`ul-${blocks.length}`}>
          {list.map((item, i) => (
            <li key={`li-${i}`}>{renderInline(item, `li-${i}`)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };

  lines.forEach((line, idx) => {
    if (line.trim().startsWith("```")) {
      if (inCode) {
        blocks.push(<pre key={`pre-${idx}`}>{code.join("\n")}</pre>);
        code = [];
        inCode = false;
      } else {
        flushList();
        inCode = true;
      }
      return;
    }
    if (inCode) {
      code.push(line);
      return;
    }
    if (/^#{1,4}\s/.test(line)) {
      flushList();
      const level = (line.match(/^#+/) || ["#"])[0].length;
      const content = line.replace(/^#+\s/, "");
      blocks.push(
        level <= 2 ? (
          <h3 key={`h-${idx}`}>{renderInline(content, `h-${idx}`)}</h3>
        ) : (
          <h4 key={`h-${idx}`}>{renderInline(content, `h-${idx}`)}</h4>
        ),
      );
      return;
    }
    if (/^[-*]\s/.test(line)) {
      list.push(line.replace(/^[-*]\s/, ""));
      return;
    }
    flushList();
    if (line.trim() === "") {
      blocks.push(<div key={`sp-${idx}`} style={{ height: 6 }} />);
    } else {
      blocks.push(<p key={`p-${idx}`}>{renderInline(line, `p-${idx}`)}</p>);
    }
  });
  flushList();
  if (inCode && code.length > 0) blocks.push(<pre key="pre-end">{code.join("\n")}</pre>);
  return <>{blocks}</>;
}
