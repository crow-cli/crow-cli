import type { ThreadMessage } from "@assistant-ui/react";
import { diffBlockOf } from "./acp-tool";

export function chatTranscript(messages: readonly ThreadMessage[]): string {
  return messages.map((message) => {
    const content = message.content.map((part) => {
      switch (part.type) {
        case "text": return part.text;
        case "reasoning": return `Thought: ${part.text}`;
        case "tool-call": {
          const diff = diffBlockOf(part);
          const result = diff?.patch ?? (typeof part.result === "string" ? part.result : JSON.stringify(part.result));
          return [`Tool: ${part.toolName}`, diff?.path, part.argsText, result].filter(Boolean).join("\n");
        }
        case "source": return `Source: ${part.title ?? part.url}`;
        case "file": case "image": return `Attachment: ${part.filename ?? part.type}`;
        default: return `[${part.type}]`;
      }
    }).join("\n\n");
    return `${message.role}:\n${content}`;
  }).join("\n\n");
}
