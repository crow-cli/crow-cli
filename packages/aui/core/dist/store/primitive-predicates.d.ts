import type { ReadonlyJSONArray, ReadonlyJSONObject } from "assistant-stream/utils";
import type { AssistantState } from "@assistant-ui/store";
/**
 * Disabled predicates shared by every binding's primitive layer. Each binding
 * consumes these as state selectors so the disabled semantics of a primitive
 * cannot drift between frameworks.
 */
export declare const composerSendDisabled: (s: AssistantState) => boolean;
export declare const composerCancelDisabled: (s: AssistantState) => boolean;
export declare const composerInputDisabled: (s: AssistantState) => boolean;
export declare const actionBarEditDisabled: (s: AssistantState) => boolean;
export declare const actionBarReloadDisabled: (s: AssistantState) => boolean;
export declare const actionBarCopyDisabled: (s: AssistantState) => boolean;
export declare const branchPickerPreviousDisabled: (s: AssistantState) => boolean;
export declare const branchPickerNextDisabled: (s: AssistantState) => boolean;
export declare const suggestionSendMode: (thread: AssistantState["thread"]) => "now" | "queued" | "blocked";
export declare const suggestionTriggerDisabled: (s: AssistantState, send: boolean) => boolean;
export declare const messageErrorText: (s: AssistantState) => string | number | boolean | ReadonlyJSONObject | ReadonlyJSONArray | undefined;
export declare const threadListLoadMoreDisabled: (s: AssistantState) => boolean;