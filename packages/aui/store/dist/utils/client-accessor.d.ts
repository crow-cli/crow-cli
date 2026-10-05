import type { AssistantClientAccessor, ClientMethods, ClientNames } from "../types/client.js";
export declare const CLIENT_ID_SYMBOL: unique symbol;
export declare const INSTANCE_TAG_SYMBOL: unique symbol;
declare const clientIdBrand: unique symbol;
type AccessorMeta = {
    name: ClientNames;
    source: ClientNames | "root";
    query: Record<string, unknown>;
};
export declare const createClientAccessor: <K extends ClientNames>(meta: AccessorMeta, read: () => ClientMethods) => AssistantClientAccessor<K>;
export declare const createErrorClientAccessor: (message: string, name: string) => AssistantClientAccessor<ClientNames>;
/**
 * Scope resolution is tri-state: available (a bound accessor), present but
 * unavailable (an error accessor with `source: null`), or absent entirely (a
 * hand-built parent chain without the scope). `isScopeAvailable` collapses
 * the last two; event subscription keeps them apart because an absent scope
 * still forwards to the parent.
 */
export declare const isScopeAvailable: <T extends {
    source: ClientNames | "root" | null;
}>(accessor: T | undefined) => accessor is T;
export declare const isScopeUnavailable: (accessor: {
    source: ClientNames | "root" | null;
} | undefined) => boolean;
/**
 * Returns the opaque identity of a bound client instance.
 *
 * The identity resolves through any forwarding layer to the underlying
 * `useClientResource` client. A scope that delegates to a replaceable client
 * yields that client's identity, which can serve as a `WeakMap` key for
 * per-client caches. Throws if the client is an accessor for an unavailable
 * scope.
 */
export declare const getClientId: (client: object) => getClientId.ClientId;
export declare namespace getClientId {
    type ClientId = {
        readonly [clientIdBrand]: never;
    };
}
/**
 * Returns the identity of the underlying client instance.
 *
 * `getClientId` follows the stable client facade, which survives a remount
 * of the resource behind it, so it cannot distinguish a structurally
 * replaced instance whose state was reset. This identity changes exactly
 * when that instance is remounted or replaced; clients without an instance
 * tag (hand-built parent chains) fall back to the facade identity.
 */
export declare const getClientInstanceId: (client: object) => getClientId.ClientId;
export {};