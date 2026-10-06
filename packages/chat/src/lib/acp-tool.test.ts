/// <reference types="bun-types" />
import { describe, expect, it } from "bun:test";
import parseDiff from "parse-diff";
import type { AcpToolCallContent } from "@assistant-ui/acp";
import { buildToolCallPart } from "../../../aui/acp/src/conversions";
import { diffBlockOf, filePathOf } from "./acp-tool";

const path = "/workspace/hello-world.txt";
const patch = "--- a/hello-world.txt\n+++ b/hello-world.txt\n@@ -1 +1 @@\n-hello, world!\n+goodbye, world!\n";
const partOf = (diff: AcpToolCallContent) => buildToolCallPart({
  toolCallId: "edit-1",
  kind: "edit",
  status: "completed",
  content: [diff],
});
const changes = (operation: string) => [{ operation, path }];

describe("ACP diff content", () => {
  it("renders v2 patches and takes paths from authoritative changes", () => {
    const part = partOf({ type: "diff", changes: changes("modify"), patch: { format: "git_patch", text: patch } });
    expect(filePathOf(part)).toBe(path);
    expect(diffBlockOf(part)).toMatchObject({ patch, isNewFile: false });
    expect(part.result).toBe(patch);
    expect(parseDiff(diffBlockOf(part)!.patch!)[0]).toMatchObject({ additions: 1, deletions: 1 });
  });

  it("distinguishes adds from modifications of empty existing files", () => {
    expect(diffBlockOf(partOf({ type: "diff", changes: changes("add") }))).toMatchObject({ isNewFile: true });
    expect(diffBlockOf(partOf({ type: "diff", changes: changes("modify") }))).toMatchObject({ isNewFile: false });
  });

  it("retains v1 before/after content", () => {
    expect(diffBlockOf(partOf({ type: "diff", path, oldText: "hello, world!", newText: "goodbye, world!" }))).toMatchObject({
      oldText: "hello, world!", newText: "goodbye, world!", isNewFile: false,
    });
    expect(diffBlockOf(partOf({ type: "diff", path, oldText: null, newText: "hello, world!" }))).toMatchObject({ isNewFile: true });
  });

  it("handles non-text changes and unsupported patch formats without interpreting them", () => {
    const part = partOf({
      type: "diff",
      changes: [{ operation: "move", oldPath: "/old.png", path: "/new.png", fileType: "binary" }],
      patch: { format: "_custom", text: "opaque" },
    });
    expect(filePathOf(part)).toBe("/new.png");
    expect(diffBlockOf(part)?.patch).toBeUndefined();
    expect(part.result).not.toContain("undefined");
  });

  it("does not label mixed multi-file changes as a new file", () => {
    const part = partOf({
      type: "diff",
      changes: [...changes("add"), { operation: "modify", path: "/other.txt" }],
      patch: null,
    });
    expect(diffBlockOf(part)?.isNewFile).toBe(false);
  });
});
