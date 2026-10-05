import type { AssistantTransportCommand, CommandQueueState, QueuedCommand } from "./types.js";
export declare const createInitialQueueState: () => CommandQueueState;
export declare const useCommandQueue: (opts: {
    onQueue: () => void;
}) => {
    readonly state: CommandQueueState;
    enqueue: (command: AssistantTransportCommand, options?: {
        schedule?: boolean;
    }) => void;
    flush: () => QueuedCommand[];
    markDelivered: () => void;
    reset: () => void;
};