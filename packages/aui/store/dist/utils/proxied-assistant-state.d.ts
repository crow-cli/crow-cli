import type { AssistantClient, AssistantState } from "../types/client.js";
/**
 * Opens a window in which a scope's state is resolved at most once per client.
 *
 * Resolving one scope walks the client accessor, the client proxy and the
 * resource output, and a notification flush re-runs every mounted selector, so
 * the same pair is resolved many times over. The window only spans a
 * synchronous flush, during which the store publishes nothing new. The
 * counters are shared by every notification manager on purpose: a flush that
 * nests inside another, from any host, advances them and so invalidates every
 * client's cache, which costs the outer flush its remaining batching and never
 * serves it a stale read.
 */
export declare const withBatchedStateReads: <T>(fn: () => T) => T;
export declare const getProxiedAssistantState: (client: AssistantClient) => AssistantState;