import { type ToolApprovalDisplay, type ToolApprovalOption, type ToolApprovalResponse } from "../../types/message.js";
import type { RespondToToolApprovalOptions } from "../interfaces/thread-runtime-core.js";
/**
 * Resolves a renderer-facing approval response (boolean, optionId, or
 * free-form answer) against the approval's request shape into the
 * runtime-facing decision shape.
 */
export declare const resolveToolApprovalResponse: (approval: {
    readonly id: string;
    readonly display?: ToolApprovalDisplay;
    readonly allowFreeform?: boolean;
    readonly options?: readonly ToolApprovalOption[];
}, response: ToolApprovalResponse) => RespondToToolApprovalOptions;