import type { QueuePlacement } from "../../runtime/queue/external-thread-queue-adapter.js";
import type { QueueItemState } from "../../runtime/queue/queue-item.js";
import type { AppendMessage } from "../../types/message.js";
export type { QueueItemState };
export type QueueItemMethods = {
    getState(): QueueItemState;
    /** @deprecated Use `move({ lane: "steer", insertAfter: null })` instead. Removal after 2026-11-05. */
    steer(): void;
    move(placement: QueuePlacement): void;
    /** Replace the message this item dispatches, keeping its place in the lane. */
    edit(message: AppendMessage): void;
    remove(): void;
};
export type QueueItemMeta = {
    source: "composer";
    query: {
        type: "index";
        index: number;
    } | {
        type: "id";
        id: string;
    };
};
export type QueueItemClientSchema = {
    methods: QueueItemMethods;
    meta: QueueItemMeta;
};