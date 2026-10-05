import { AssistantStream } from "../AssistantStream.js";
import type { AssistantStreamChunk } from "../AssistantStreamChunk.js";
import { type TextStreamController } from "./text.js";
import { type ToolCallStreamController } from "./tool-call.js";
import type { DataPart, FilePart, SourcePart } from "../utils/types.js";
import type { ReadonlyJSONObject, ReadonlyJSONValue } from "../../utils/json/json-value.js";
import type { ToolResponseLike } from "../tool/ToolResponse.js";
type ToolCallPartInit = {
    toolCallId?: string;
    toolName: string;
    argsText?: string;
    args?: ReadonlyJSONObject;
    response?: ToolResponseLike<ReadonlyJSONValue>;
};
type ReasoningPartInit = {
    unstable_summary?: string;
};
/**
 * Imperative writer for constructing an {@link AssistantStream}.
 *
 * The controller handles part boundaries for common streaming operations. Use
 * `appendText` and `appendReasoning` for simple token streams, or open explicit
 * parts with `addTextPart` and `addToolCallPart` when you need direct control.
 */
export type AssistantStreamController = {
    /** Appends text to the current text part, opening one if needed. */
    appendText(textDelta: string): void;
    /**
     * Appends reasoning text to the current reasoning part, opening one if
     * needed. Supplying options opens a new part and applies them to it, so a
     * summary always lands on a part of its own.
     */
    appendReasoning(reasoningDelta: string, options?: ReasoningPartInit): void;
    /** Appends a source citation part to the stream. */
    appendSource(options: SourcePart): void;
    /** Appends a file part to the stream. */
    appendFile(options: FilePart): void;
    /** Appends a named data part to the stream. */
    appendData(options: DataPart): void;
    /**
     * Opens a text part and returns its writer.
     *
     * Close the returned controller when the text part is complete. Opening a new
     * part through this controller closes any implicit text or reasoning append
     * part first.
     */
    addTextPart(): TextStreamController;
    /**
     * Opens a reasoning part and returns its writer.
     *
     * Use the options object to provide an app-authored summary for the part.
     * A summary makes the data stream emit a reasoning part-start frame, which
     * decoders older than that frame reject, so a stream only requires a current
     * client once it uses the field.
     */
    addReasoningPart(options?: ReasoningPartInit): TextStreamController;
    /**
     * Opens a tool-call part by tool name and returns its writer.
     *
     * A tool call id is generated automatically. Use the object overload when the
     * caller already has an id, initial args, args text, or response.
     */
    addToolCallPart(options: string): ToolCallStreamController;
    /**
     * Opens a tool-call part and returns its writer.
     *
     * Use this overload to provide a stable `toolCallId`, initial arguments,
     * streamed argument text, or an immediate {@link ToolResponseLike}.
     */
    addToolCallPart(options: ToolCallPartInit): ToolCallStreamController;
    /** Enqueues a raw protocol chunk. Prefer higher-level helpers when possible. */
    enqueue(chunk: AssistantStreamChunk): void;
    /**
     * Merges another assistant stream into this stream.
     *
     * Paths from the merged stream are remapped so its parts appear at the next
     * available position in this controller's output.
     */
    merge(stream: AssistantStream): void;
    /** Closes any active part and finishes the stream. */
    close(): void;
    /**
     * Returns a controller that writes child parts with `parentId` attached.
     *
     * Use this for nested or related parts that should be associated with an
     * existing message or part in downstream renderers.
     */
    withParentId(parentId: string): AssistantStreamController;
};
type AssistantStreamOptions = {
    strict?: boolean | undefined;
};
/**
 * Creates an {@link AssistantStream} and writes to it with an
 * {@link AssistantStreamController}.
 *
 * The callback may write synchronously or asynchronously. If it throws while
 * the stream is open, an `error` chunk is emitted. Failures after an explicit
 * close are logged, while failures after consumer cancellation are discarded.
 * When the callback settles, the stream is closed automatically unless the
 * controller was already closed.
 */
export declare function createAssistantStream(callback: (controller: AssistantStreamController) => PromiseLike<void> | void, options?: AssistantStreamOptions): AssistantStream;
/**
 * Creates an {@link AssistantStream} together with the controller used to
 * write into it.
 *
 * Use this when the stream needs to be returned before all writers are known.
 * Closing the returned controller finishes the paired stream.
 */
export declare function createAssistantStreamController(options?: AssistantStreamOptions): readonly [AssistantStream, AssistantStreamController];
export {};