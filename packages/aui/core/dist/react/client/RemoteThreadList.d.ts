import type { ClientOutput } from "@assistant-ui/store";
import type { RemoteThreadListAdapter } from "../../runtimes/remote-thread-list/types.js";
import { type InMemoryThreadListProps } from "./InMemoryThreadList.js";
export type RemoteThreadListProps = {
    /**
     * Swapping this to a different backing store does not reload the list. Call `reload()` after a genuine swap. A recreated object for the same store is a no-op. `reload()` after a different adapter instance resets selection and cached records before loading.
     */
    adapter: RemoteThreadListAdapter;
    /**
     * Factory for the visible thread. Per-thread history reload requires a
     * resource keyed by thread id (`withKey(id, thread(...))`). An unkeyed
     * factory keeps one instance across switches, so a mount-once history
     * loader will not fetch the next thread.
     */
    thread: InMemoryThreadListProps["thread"];
    threadId?: string | undefined;
    onThreadIdChange?: ((threadId: string | undefined) => void) | undefined;
    onSwitchToThread?: ((threadId: string) => void) | undefined;
    onSwitchToNewThread?: (() => void) | undefined;
    /** Called after the backing adapter successfully deletes the thread. */
    onDelete?: ((threadId: string) => void) | undefined;
    /**
     * Keeps every thread the session switched to mounted, so a run continues
     * after the user switches away, per-item `isRunning` reflects background
     * runs, and a freshly initialized thread generates its title automatically.
     * A body unmounts on delete, detach, or an adapter replacement (`reload()`
     * after swapping the adapter); visited threads otherwise stay mounted for
     * the client's lifetime. Each body reads its own thread through the ambient
     * `threadListItem` scope, and `unstable_useAdapters` runs once per mounted
     * body. Off (the default), only the visible thread is mounted and a switch
     * unmounts it. The mode is fixed at mount.
     */
    backgroundThreads?: boolean | undefined;
};
/**
 * `AuiConfig` `threads` entry backed by a `RemoteThreadListAdapter`. Thread
 * bodies are born from the `thread` factory inside the client tree, so any
 * `AssistantClient` host can run a remote or cloud list. Per-thread history
 * and attachments come from `unstable_useAdapters`. `useRemoteThreadListRuntime`
 * uses the same hook when `unstable_Provider` is omitted. Key the factory
 * with `withKey` so history reloads when the visible thread changes.
 * With `backgroundThreads`, every visited thread stays mounted: runs continue
 * across switches, per-item `isRunning` is live, and freshly initialized
 * threads title themselves.
 */
export declare const RemoteThreadList: import("@assistant-ui/tap").Resource<ClientOutput<"threads">, [props: RemoteThreadListProps]>;