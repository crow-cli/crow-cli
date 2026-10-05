import type { AppendMessage } from "../../types/message.js";
import type { ExternalThreadQueueAdapter } from "./external-thread-queue-adapter.js";
export type MessageQueueDriver = {
    /**
     * A synchronous throw is treated as a run that never started and restores
     * the message. A driver that already started work must call `notifyBusy`
     * before throwing.
     */
    run: (message: AppendMessage, options: {
        steer: boolean;
    }) => void;
    /** When omitted, steering degrades to "process next" instead of interrupting. */
    cancel?: (() => void) | undefined;
};
export type MessageQueueController = {
    readonly adapter: ExternalThreadQueueAdapter;
    hold: () => void;
    release: () => void;
    /** Mark a run as in flight so concurrent sends buffer; call on the rising edge. */
    notifyBusy: () => void;
    /** Advances to the next pending message; call on the run's falling edge. */
    notifyIdle: () => void;
    /**
     * Pauses queue advance for a user-initiated cancel, so the cancelled run's
     * settle keeps the pending items instead of dispatching the next one; the
     * next explicit send or run start re-arms draining. Call before aborting
     * the run.
     */
    notifyCancelled: () => void;
    /** Empties both lanes without dispatching. */
    clear: () => void;
    subscribe: (callback: () => void) => () => void;
};
export declare const createMessageQueue: (driver: MessageQueueDriver) => MessageQueueController;