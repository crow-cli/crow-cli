import type { Tool } from "./tool-types.js";
import { ToolExecutionStream } from "./ToolExecutionStream.js";
import type { AssistantMessage } from "../utils/types.js";
export declare function unstable_runPendingTools(message: AssistantMessage, tools: Record<string, Tool> | undefined, abortSignal: AbortSignal, human: (toolCallId: string, payload: unknown) => Promise<unknown>): Promise<AssistantMessage>;
export type ToolResultStreamOptions = {
    /** Called after frontend tool execution starts. Callback failures are reported without interrupting the tool. */
    onExecutionStart?: (toolCallId: string, toolName: string) => void;
    /** Called after frontend tool execution finishes or fails. Callback failures are reported without changing the result. */
    onExecutionEnd?: (toolCallId: string, toolName: string) => void;
};
/**
 * Transform stream that executes frontend tools and appends tool results.
 *
 * The transform watches streamed tool-call arguments, runs the matching
 * frontend tool once its arguments are complete, and emits a result chunk for
 * the tool call. Backend and human tools pass through according to their tool
 * definition.
 *
 * @param tools Tool registry or function returning the current registry.
 * @param abortSignal Signal, or signal getter, used for the current run.
 * @param human Callback used to resolve human-tool requests from UI input.
 * @param options Optional execution lifecycle callbacks.
 */
export declare function toolResultStream(tools: Record<string, Tool> | (() => Record<string, Tool> | undefined) | undefined, abortSignal: AbortSignal | (() => AbortSignal), human: (toolCallId: string, payload: unknown) => Promise<unknown>, options?: ToolResultStreamOptions): ToolExecutionStream;