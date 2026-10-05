//#region src/core/serialization/data-stream/chunk-types.ts
const DataStreamStreamChunkType = {
	TextDelta: "0",
	Data: "2",
	Error: "3",
	Annotation: "8",
	ToolCall: "9",
	ToolCallResult: "a",
	StartToolCall: "b",
	ToolCallArgsTextDelta: "c",
	FinishMessage: "d",
	FinishStep: "e",
	StartStep: "f",
	ReasoningDelta: "g",
	Source: "h",
	RedactedReasoning: "i",
	ReasoningSignature: "j",
	File: "k",
	AuiUpdateStateOperations: "aui-state",
	AuiTextDelta: "aui-text-delta",
	AuiReasoningDelta: "aui-reasoning-delta",
	AuiDataPart: "aui-data",
	AuiReasoningPartStart: "aui-reasoning-part-start"
};
//#endregion
export { DataStreamStreamChunkType };
