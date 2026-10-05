import type { Unstable_ToolInteraction, Unstable_ToolInteractionInput, Unstable_ToolInteractionLog } from "../../types/message.js";
export declare const TOOL_INTERACTION_LIMITS: {
    readonly entries: 32;
    readonly payloadLength: 16384;
    readonly logLength: 65536;
};
export declare function createToolInteraction(input: Unstable_ToolInteractionInput, occurredAt?: number): Unstable_ToolInteraction;
export declare function appendToolInteraction(log: Unstable_ToolInteractionLog | undefined, interaction: Unstable_ToolInteraction): Unstable_ToolInteractionLog;
export declare function readToolInteractionLog(value: unknown): Unstable_ToolInteractionLog | undefined;