import { type ResourceElement } from "@assistant-ui/tap";
import type { AssistantClient, ClientNames, ClientMethods } from "./types/client.js";
import type { AuiConfig } from "./AuiConfig.js";
import { type NotificationManager } from "./utils/NotificationManager.js";
export type ClientRef = {
    parent: AssistantClient;
    current: AssistantClient | null;
};
type ScopeElement = ResourceElement<ClientMethods>;
export type ScopeEntry = [name: ClientNames, element: ScopeElement];
export declare const applyTransformScopes: (clients: useAui.Props, parent: AssistantClient) => Record<string, ScopeElement>;
export declare const useAuiRoot: ({ parent, entries, clientRef, notifications, }: {
    parent: AssistantClient;
    entries: ScopeEntry[];
    clientRef: ClientRef;
    notifications: NotificationManager;
}) => {
    client: AssistantClient;
};
type ScopedAuiClient = {
    client: AssistantClient;
    effects?: () => void;
};
export declare const useConfiguredAui: (parent: AssistantClient, clients: AuiConfig.Input, destroySignal?: AbortSignal) => ScopedAuiClient;
export declare namespace useAui {
    type Props = AuiConfig.Input;
}
/**
 * Returns the current `AssistantClient` from context.
 *
 * Read the client supplied by the nearest {@link AuiProvider} or
 * {@link AssistantRuntimeProvider}, then access a scope on it —
 * `aui.thread`, `aui.composer`, `aui.message`, and so on. Pair
 * with {@link useAuiState} to read reactive state and {@link useAuiEvent}
 * to subscribe to events. The returned client also exposes lower-level
 * methods such as `aui.on(...)` and `aui.subscribe(...)`; prefer
 * `useAuiEvent` for React event subscriptions.
 *
 * Rendered outside a provider, the returned client's scope accessors
 * throw a descriptive error whenever they are called.
 *
 * @example
 * ```tsx
 * const aui = useAui();
 *
 * const onSend = () => aui.composer.send();
 * const onCancel = () => aui.thread.cancelRun();
 * ```
 *
 * @example
 * ```tsx
 * // Combine with useAuiState to drive disabled state.
 * const aui = useAui();
 * const isRunning = useAuiState((s) => s.thread.isRunning);
 *
 * return (
 *   <button disabled={isRunning} onClick={() => aui.composer.send()}>
 *     Send
 *   </button>
 * );
 * ```
 */
export declare function useAui(): AssistantClient;
/**
 * Extends the parent `AssistantClient` with additional scopes.
 *
 * Advanced overload used when building primitives or providers — for example,
 * when a custom provider needs to register a `message`, `part`, or other scope
 * onto the client visible to its descendants. Application code rarely reaches
 * for this; use {@link useAui} with no arguments to read the existing client.
 *
 * Derived scopes are resolved during render and bound into the returned
 * client. The client is immutable: state updates inside a bound instance
 * never change its identity, while a structural change (the scope resolving
 * to a different instance) produces a new client and re-renders consumers
 * through React.
 *
 * @example
 * ```tsx
 * const aui = useAui({
 *   message: Derived({
 *     source: "thread",
 *     query: { index: 0 },
 *     get: (aui) => aui.thread.message({ index: 0 }),
 *   }),
 * });
 *
 * const role = useAuiState((s) => s.message.role);
 * ```
 *
 * @deprecated Build a config in the component body (`const aui = useAui();
 * const config = AuiConfig({ ... })`) and render `<AuiProvider extends={aui}
 * config={config}>` instead; it creates the client and provides it to the
 * subtree in one step.
 */
export declare function useAui(clients: useAui.Props): AssistantClient;
export {};