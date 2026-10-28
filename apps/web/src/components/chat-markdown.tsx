"use client";

import { code } from "@streamdown/code";
import { Streamdown } from "streamdown";

const allowedProtocols = new Set(["http:", "https:", "mailto:"]);

interface ChatMarkdownProps {
  content: string;
  isStreaming?: boolean;
}

export function ChatMarkdown({
  content,
  isStreaming = false,
}: ChatMarkdownProps) {
  return (
    <Streamdown
      className="chat-markdown text-sm leading-6 text-slate-200"
      mode={isStreaming ? "streaming" : "static"}
      isAnimating={isStreaming}
      plugins={{ code }}
      skipHtml
      components={{ img: () => null }}
      urlTransform={(url, key) => {
        if (key === "src") return "";
        const protocol = /^([a-z][a-z\d+.-]*:)/i.exec(url)?.[1]?.toLowerCase();
        return protocol && !allowedProtocols.has(protocol) ? "" : url;
      }}
    >
      {content}
    </Streamdown>
  );
}
