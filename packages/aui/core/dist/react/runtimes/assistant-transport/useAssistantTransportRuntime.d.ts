import type { AssistantRuntime } from "../../../runtime/api/assistant-runtime.js";
import type { AssistantTransportOptions, AssistantTransportCommand } from "./types.js";
import type { UserExternalState } from "../../../types/augmentations.js";
export declare const useAssistantTransportSendCommand: () => (command: AssistantTransportCommand) => void;
export declare function useAssistantTransportState(): UserExternalState;
export declare function useAssistantTransportState<T>(selector: (state: UserExternalState) => T): T;
/**
 * @alpha This is an experimental API that is subject to change.
 */
export declare const useAssistantTransportRuntime: <T>(options: AssistantTransportOptions<T>) => AssistantRuntime;