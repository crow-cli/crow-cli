import type { ThreadHistoryAdapter } from "../../adapters/thread-history.js";
import type { ThreadRuntimeCore, Unstable_RecordToolInteractionOptions } from "../../runtime/interfaces/thread-runtime-core.js";
export declare class ExternalStoreHistoryCopy {
    private thread;
    private history;
    private lastHistory;
    private session;
    private copied;
    private failedIds;
    private interactions;
    private overlaid;
    private pending;
    private inFlight;
    private timer;
    private waiters;
    private warned;
    private signature;
    private branch;
    private seed;
    attach(thread: ThreadRuntimeCore, history: ThreadHistoryAdapter): () => void;
    recordInteraction: (options: Unstable_RecordToolInteractionOptions) => Promise<void>;
    private schedule;
    private flush;
}