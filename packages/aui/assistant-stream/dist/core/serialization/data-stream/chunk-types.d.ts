import type { ReadonlyJSONObject, ReadonlyJSONValue } from "../../../utils/json/json-value.js";
import type { GorpStreamOperation } from "../../gorp/types.js";
import type { ToolModelContentPart } from "../../tool/tool-types.js";
export type DataStreamChunk = {
    [K in DataStreamStreamChunkType]: {
        type: K;
        value: DataStreamStreamChunkValue[K];
    };
}[DataStreamStreamChunkType];
type LanguageModelV1FinishReason = "stop" | "length" | "content-filter" | "tool-calls" | "error" | "other" | "unknown";
type LanguageModelV1Usage = {
    inputTokens: number;
    outputTokens: number;
};
export declare const DataStreamStreamChunkType: {
    readonly TextDelta: "0";
    readonly Data: "2";
    readonly Error: "3";
    readonly Annotation: "8";
    readonly ToolCall: "9";
    readonly ToolCallResult: "a";
    readonly StartToolCall: "b";
    readonly ToolCallArgsTextDelta: "c";
    readonly FinishMessage: "d";
    readonly FinishStep: "e";
    readonly StartStep: "f";
    readonly ReasoningDelta: "g";
    readonly Source: "h";
    readonly RedactedReasoning: "i";
    readonly ReasoningSignature: "j";
    readonly File: "k";
    readonly AuiUpdateStateOperations: "aui-state";
    readonly AuiTextDelta: "aui-text-delta";
    readonly AuiReasoningDelta: "aui-reasoning-delta";
    readonly AuiDataPart: "aui-data";
    readonly AuiReasoningPartStart: "aui-reasoning-part-start";
};
export type DataStreamStreamChunkType = (typeof DataStreamStreamChunkType)[keyof typeof DataStreamStreamChunkType];
type DataStreamStreamChunkValue = {
    [DataStreamStreamChunkType.TextDelta]: string;
    [DataStreamStreamChunkType.Data]: ReadonlyJSONValue[];
    [DataStreamStreamChunkType.Annotation]: ReadonlyJSONValue[];
    [DataStreamStreamChunkType.ToolCall]: {
        toolCallId: string;
        toolName: string;
        args: ReadonlyJSONObject;
    };
    [DataStreamStreamChunkType.StartToolCall]: {
        toolCallId: string;
        toolName: string;
        parentId?: string;
    };
    [DataStreamStreamChunkType.ToolCallArgsTextDelta]: {
        toolCallId: string;
        argsTextDelta: string;
        isFinal?: boolean;
    };
    [DataStreamStreamChunkType.ToolCallResult]: {
        toolCallId: string;
        result: ReadonlyJSONValue;
        artifact?: ReadonlyJSONValue | undefined;
        isError?: boolean;
        isPreliminary?: boolean;
        modelContent?: readonly ToolModelContentPart[];
    };
    [DataStreamStreamChunkType.Error]: string;
    [DataStreamStreamChunkType.FinishStep]: {
        finishReason: LanguageModelV1FinishReason;
        usage: LanguageModelV1Usage;
        isContinued: boolean;
    };
    [DataStreamStreamChunkType.FinishMessage]: {
        finishReason: LanguageModelV1FinishReason;
        usage: LanguageModelV1Usage;
    };
    [DataStreamStreamChunkType.StartStep]: {
        messageId: string;
    };
    [DataStreamStreamChunkType.ReasoningDelta]: string;
    [DataStreamStreamChunkType.Source]: {
        sourceType: "url";
        id: string;
        url: string;
        title?: string;
        parentId?: string;
    };
    [DataStreamStreamChunkType.RedactedReasoning]: {
        data: string;
    };
    [DataStreamStreamChunkType.ReasoningSignature]: {
        signature: string;
    };
    [DataStreamStreamChunkType.File]: {
        data: string;
        mimeType: string;
        parentId?: string;
    };
    [DataStreamStreamChunkType.AuiUpdateStateOperations]: GorpStreamOperation[];
    [DataStreamStreamChunkType.AuiTextDelta]: {
        textDelta: string;
        parentId: string;
    };
    [DataStreamStreamChunkType.AuiReasoningDelta]: {
        reasoningDelta: string;
        parentId: string;
    };
    [DataStreamStreamChunkType.AuiReasoningPartStart]: {
        unstable_summary?: string;
        parentId?: string;
    };
    [DataStreamStreamChunkType.AuiDataPart]: {
        name: string;
        data: ReadonlyJSONValue;
        parentId?: string;
    };
};
export {};