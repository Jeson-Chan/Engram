/** 完整 Markdown 渲染(marked 解析 + DOMPurify 消毒,零 XSS 面)。

替换 web-pixel-flavor 前的自写极简版:支持表格/链接/引用块/任务列表/
删除线等 GFM 全集——深度研究回复里的表格不再掉成纯文本。
 */

import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({ gfm: true, breaks: true });

export function Markdown({ text }: { text: string }) {
  if (!text) return null;
  const raw = marked.parse(text, { async: false }) as string;
  const clean = DOMPurify.sanitize(raw, {
    // 研究工具不放开任何主动交互标签
    FORBID_TAGS: ["script", "style", "iframe", "object", "embed", "form"],
    FORBID_ATTR: ["onerror", "onclick", "onload", "onmouseover"],
  });
  return (
    <div
      className="markdown-body"
      data-testid="markdown-body"
      dangerouslySetInnerHTML={{ __html: clean }}
    />
  );
}
