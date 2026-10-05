import type { ReadonlyJSONValue } from "../../utils/json/json-value.js";
import type { ToolModelContentPart } from "./tool-types.js";
declare const TOOL_RESPONSE_SYMBOL: unique symbol;
/** Stand-in result for a tool that completed without returning a value. */
export declare const NO_RESULT = "<no result>";
/**
 * Shape accepted anywhere a {@link ToolResponse} can be returned.
 */
export type ToolResponseLike<TResult> = {
    /** UI-visible tool result value. */
    result: TResult;
    /**
     * Optional UI-only artifact associated with the result.
     *
     * Artifacts are useful for large or structured data that should be available
     * to renderers without necessarily being sent back to the model.
     */
    artifact?: ReadonlyJSONValue | undefined;
    /** Marks the tool result as an error result. */
    isError?: boolean | undefined;
    /**
     * Marks the result as interim while the tool call keeps running. Honored by
     * stream controllers, which can send more responses; a tool's `execute`
     * result is always final and ignores it.
     */
    isPreliminary?: boolean | undefined;
    /**
     * Explicit model-visible content to send back after the tool call.
     *
     * When omitted, assistant-ui derives model output from `result` or a tool's
     * {@link ToolModelOutputFunction}.
     */
    modelContent?: readonly ToolModelContentPart[] | undefined;
    /** Optional provider-specific message payload associated with the tool result. */
    messages?: ReadonlyJSONValue | undefined;
};
/**
 * Tool result wrapper for separating UI-visible output from model-visible
 * output.
 *
 * Return `ToolResponse` from a tool when you need to attach an artifact, mark
 * the result as an error, or control the content sent back to the model.
 *
 * @example
 * ```ts
 * return new ToolResponse({
 *   result: { title: "Report ready" },
 *   artifact: { reportId },
 *   modelContent: [{ type: "text", text: "The report is ready." }],
 * });
 * ```
 */
export declare class ToolResponse<TResult> {
    get [TOOL_RESPONSE_SYMBOL](): boolean;
    readonly artifact?: ReadonlyJSONValue;
    readonly result: TResult;
    readonly isError: boolean;
    readonly isPreliminary?: boolean;
    readonly modelContent?: readonly ToolModelContentPart[];
    readonly messages?: ReadonlyJSONValue;
    constructor(options: ToolResponseLike<TResult>);
    static [Symbol.hasInstance](obj: unknown): obj is ToolResponse<ReadonlyJSONValue>;
    /**
     * Converts a plain tool return value into a {@link ToolResponse}.
     *
     * Existing `ToolResponse` instances are returned unchanged. `undefined`
     * becomes the string `"<no result>"` so downstream protocol chunks always
     * carry a concrete result.
     */
    static toResponse(result: any | ToolResponse<any>): ToolResponse<any>;
}
export {};