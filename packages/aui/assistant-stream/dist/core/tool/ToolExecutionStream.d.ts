import type { AssistantStreamChunk } from "../AssistantStreamChunk.js";
import { PipeableTransformStream } from "../utils/stream/PipeableTransformStream.js";
import type { ReadonlyJSONObject, ReadonlyJSONValue } from "../../utils/json/json-value.js";
import { ToolResponse } from "./ToolResponse.js";
import type { ToolCallReader } from "./tool-types.js";
type ToolCallback = (toolCall: {
    toolCallId: string;
    toolName: string;
    args: ReadonlyJSONObject;
}) => Promise<ToolResponse<ReadonlyJSONValue>> | ToolResponse<ReadonlyJSONValue> | undefined;
type ToolStreamCallback = <TArgs extends ReadonlyJSONObject = ReadonlyJSONObject, TResult extends ReadonlyJSONValue = ReadonlyJSONValue>(toolCall: {
    reader: ToolCallReader<TArgs, TResult>;
    toolCallId: string;
    toolName: string;
}) => void;
type ToolExecutionOptions = {
    execute: ToolCallback;
    streamCall: ToolStreamCallback;
    onExecutionStart?: ((toolCallId: string, toolName: string) => void) | undefined;
    onExecutionEnd?: ((toolCallId: string, toolName: string) => void) | undefined;
};
export declare class ToolExecutionStream extends PipeableTransformStream<AssistantStreamChunk, AssistantStreamChunk> {
    constructor(options: ToolExecutionOptions);
}
export {};