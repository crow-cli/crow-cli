import type { AssistantClient } from "../types/client.js";
/** Default context value - throws "wrap in AuiProvider" error */
export declare const DefaultAssistantClient: AssistantClient;
/** Root prototype for created clients - throws "scope not defined" error */
export declare const createRootAssistantClient: () => AssistantClient;
/**
 * React Context for the AssistantClient
 */
export declare const AssistantContext: import("react").Context<AssistantClient>;
export declare const getTapEffects: (client: AssistantClient) => (() => void);
/**
 * Records the tap host's effects callback for clients created by the
 * deprecated `useAui({...})` overload; the AuiProvider the client is passed
 * to mounts the host's commit ahead of its children's effects.
 */
export declare const setTapEffects: (client: AssistantClient, effects: () => void) => void;
export declare const useAssistantContextValue: () => AssistantClient;
export declare const useAssistantContextProvider: <T>(value: AssistantClient, fn: () => T) => T;