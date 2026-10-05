import { type ResourceElement } from "@assistant-ui/tap";
import type { AssistantClient, ClientNames, AssistantClientAccessor, ClientMeta } from "./types/client.js";
type DerivedInstance<K extends ClientNames> = ReturnType<AssistantClientAccessor<K>>;
export declare const useDerived: <K extends ClientNames>({ get, }: Derived.Props<K>) => DerivedInstance<K>;
/**
 * Creates a derived client field whose resolved instance is bound into the
 * client returned by `useAui`; a structural swap produces a new client through
 * a React re-render. `get` must return a client created via
 * `useClientResource` (or `useClientLookup`/`useClientList`).
 *
 * @example
 * ```tsx
 * const aui = useAui();
 * const config = AuiConfig({
 *   message: Derived({
 *     source: "thread",
 *     query: { index: 0 },
 *     get: (aui) => aui.thread.message({ index: 0 }),
 *   }),
 * });
 *
 * <AuiProvider extends={aui} config={config}>{children}</AuiProvider>;
 * ```
 */
export declare const Derived: <K extends ClientNames>(config: Derived.Props<K>) => DerivedElement<K>;
export type DerivedElement<K extends ClientNames> = ResourceElement<DerivedInstance<K>>;
export declare namespace Derived {
    /**
     * Props passed to a derived client resource element.
     */
    type Props<K extends ClientNames> = {
        get: (client: AssistantClient) => ReturnType<AssistantClientAccessor<K>>;
    } & ClientMeta<K>;
}
export {};