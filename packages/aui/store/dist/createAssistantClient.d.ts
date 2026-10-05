import type { AssistantClient, Unsubscribe } from "./types/client.js";
import type { AuiConfig } from "./AuiConfig.js";
/**
 * A live view onto an `AssistantClient` whose identity may change over time.
 *
 * `getClient` returns the current client; `subscribe` fires after every state
 * or structural update. An {@link AssistantClientHandle} is itself a source,
 * so handles nest directly as the `parent` of another handle.
 */
export type AssistantClientSource = {
    getClient(): AssistantClient;
    subscribe(listener: () => void): Unsubscribe;
};
export type AssistantClientHandle = AssistantClientSource & {
    destroy(): void;
};
/**
 * A live view onto a config whose entries may change over time.
 *
 * `getConfig` returns the current config; `subscribe` fires after every
 * change. The root re-reads the config on each notification: a scope that
 * keeps its key keeps its state while its element args update, and added or
 * removed keys mount and unmount their scopes.
 */
export type AssistantConfigSource = {
    getConfig(): AuiConfig.Input;
    subscribe(listener: () => void): Unsubscribe;
};
/**
 * Creates an `AssistantClient` outside any UI framework.
 *
 * The client's scopes run as tap resources inside a standalone tap root; no
 * React renderer is involved. This is the construction seam for non-React
 * bindings: a framework bridge creates the handle, reads the current client
 * with `getClient`, re-reads it whenever `subscribe` fires (a structural
 * change produces a new client object, a value-only update keeps its
 * identity), and holds a subscription for as long as it needs the client
 * alive.
 *
 * The handle's lifecycle rides its subscriber count. Scopes render lazily on the first read and mount when the first subscriber attaches; state updates before that throw, so an imperative consumer without a reactive framework holds a no-op subscription. When the last subscriber releases, the root soft-unmounts on the next task: effects other than insertion effects clean up, state is retained, and a later subscriber remounts the same scopes. `destroy` is the permanent teardown: it aborts the destroy signal and synchronously releases every scope, insertion effects included, whether or not subscribers are attached. A bridge that only releases its subscriptions keeps insertion effects mounted until `destroy`.
 *
 * The parent may be a plain client or another source/handle. Passing a source
 * keeps the child bound to the parent's current client across the parent's
 * structural changes without remounting the child's scopes.
 *
 * The config may be a plain value, captured at creation, or an
 * {@link AssistantConfigSource} that is re-read in the root render whenever it
 * notifies, so a binding can deliver config changes (updated element args,
 * added or removed scopes) without remounting the surviving scopes.
 */
export declare const createAssistantClient: (config: AuiConfig.Input | AssistantConfigSource, options?: {
    parent?: AssistantClient | AssistantClientSource | undefined;
}) => AssistantClientHandle;