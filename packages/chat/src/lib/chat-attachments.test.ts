/// <reference types="bun-types" />
import { expect, it } from "bun:test";
import { chatAttachments } from "./chat-attachments";

it("reads real image and text files through the existing assistant-ui adapters", async () => {
  const image = await chatAttachments.add({ file: new File([new Uint8Array([1, 2, 3])], "image.png", { type: "image/png" }) });
  if (Symbol.asyncIterator in image) throw new Error("Expected a pending attachment");
  expect((await chatAttachments.send(image)).content).toEqual([{ type: "image", image: "data:image/png;base64,AQID" }]);
  const text = await chatAttachments.add({ file: new File(["hello, world!"], "note.txt", { type: "text/plain" }) });
  if (Symbol.asyncIterator in text) throw new Error("Expected a pending attachment");
  expect((await chatAttachments.send(text)).content).toEqual([{ type: "text", text: '<attachment name="note.txt">\nhello, world!\n</attachment>' }]);
});
