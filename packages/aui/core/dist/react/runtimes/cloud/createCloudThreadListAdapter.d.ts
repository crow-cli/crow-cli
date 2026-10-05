import { type RefObject } from "react";
import { AssistantCloud, type SdkIdentity } from "assistant-cloud";
import type { RemoteThreadListAdapter, RuntimeAdapters } from "../../../runtimes/remote-thread-list/types.js";
type ThreadData = {
    externalId: string | undefined;
};
export type CloudThreadListAdapterOptions = {
    cloud?: AssistantCloud | undefined;
    sdk?: SdkIdentity | undefined;
    /** Returns the external id for a new cloud thread, which is created once this resolves; `threadId` is the `id` of the thread list item being saved. */
    create?: ((threadId: string) => Promise<ThreadData>) | undefined;
    delete?: ((threadId: string) => Promise<void>) | undefined;
    /** Creates each cloud thread with `upsert`, so a retried create reuses the thread that already has the external id `create` returned; set it when that id names exactly one conversation. */
    upsert?: boolean | undefined;
};
export declare const autoCloud: AssistantCloud | undefined;
export declare const useCloudRuntimeAdapters: (cloudRef: RefObject<AssistantCloud>) => RuntimeAdapters;
/**
 * Builds the `RemoteThreadListAdapter` for an assistant-cloud backend without
 * requiring a hook call site, so plain code (a Vue or Svelte setup function,
 * a module-level config) can construct it. Options are read through the
 * getter on every call, so a stable adapter can follow changing `create` and
 * `delete` callbacks; swapping to a different `cloud` instance requires a new
 * adapter (and `reload()` on the list). Without a `cloud` instance (and
 * without `NEXT_PUBLIC_ASSISTANT_BASE_URL`), the adapter falls back to an
 * in-memory list. `useCloudThreadListAdapter` wraps this for the React
 * hook signature.
 */
export declare const createCloudThreadListAdapter: (options: CloudThreadListAdapterOptions | (() => CloudThreadListAdapterOptions)) => RemoteThreadListAdapter;
export {};