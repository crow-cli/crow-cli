/// <reference types="bun-types" />
import { expect, it } from "bun:test";
import { buildToolCallPart } from "../../../aui/acp/src/conversions";
import { chatTranscript } from "./chat-transcript";

it("exposes messages, reasoning and ACP patch content without visual formatting", () => {
  const patch = "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-before\n+after\n";
  const tool = buildToolCallPart({
    toolCallId: "edit-1", kind: "edit", status: "completed", title: "edit a.txt",
    content: [{ type: "diff", changes: [{ operation: "modify", path: "/a.txt" }], patch: { format: "git_patch", text: patch } }],
  });
  const transcript = chatTranscript([{
    id: "message-1", role: "assistant", createdAt: new Date(),
    content: [{ type: "text", text: "Updated the file." }, { type: "reasoning", text: "Checking changes." }, tool],
    status: { type: "complete", reason: "stop" },
    metadata: { custom: {}, unstable_state: null, unstable_annotations: [], unstable_data: [], steps: [] },
  }]);
  expect(transcript).toContain("assistant:\nUpdated the file.");
  expect(transcript).toContain("Thought: Checking changes.");
  expect(transcript).toContain("/a.txt");
  expect(transcript).toContain(patch);
});
