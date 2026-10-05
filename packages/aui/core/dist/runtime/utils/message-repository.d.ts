import type { ThreadMessage } from "../../types/message.js";
import type { RunConfig } from "../../types/message.js";
import type { ThreadMessageLike } from "./thread-message-like.js";
export type ExportedMessageRepositoryItem = {
    message: ThreadMessage;
    parentId: string | null;
    runConfig?: RunConfig;
};
export type ExportedMessageRepository = {
    headId?: string | null;
    messages: Array<{
        message: ThreadMessage;
        parentId: string | null;
        runConfig?: RunConfig;
    }>;
};
export declare const ExportedMessageRepository: {
    fromArray: (messages: readonly ThreadMessageLike[]) => ExportedMessageRepository;
    fromBranchableArray: (items: readonly {
        message: ThreadMessageLike;
        parentId: string | null;
    }[], options?: {
        headId?: string | null;
    }) => ExportedMessageRepository;
};
export declare const withoutOrphanedMessages: (repository: ExportedMessageRepository) => {
    repository: ExportedMessageRepository;
    droppedIds: string[];
};
export declare class MessageRepository {
    private messages;
    private head;
    private root;
    private updateLevels;
    private selectPathTo;
    private performOp;
    private _messages;
    get headId(): string | null;
    get canonicalHeadId(): string | null;
    getMessages(headId?: string): readonly ThreadMessage[];
    addOrUpdateMessage(parentId: string | null, message: ThreadMessage): void;
    getMessage(messageId: string): {
        parentId: string | null;
        message: ThreadMessage;
        index: number;
    };
    deleteMessage(messageId: string, replacementId?: string | null | undefined): void;
    hasChildren(messageId: string): boolean;
    getBranches(messageId: string): string[];
    /**
     * Evicts optimistic messages (`metadata.isOptimistic`) on the branch the head
     * just moved away from. Only that branch is walked, so an optimistic message
     * added off the head branch (such as the server-id copy that replaces a
     * client-id placeholder before the head moves to it) is kept until a
     * `switchToBranch` or `resetHead` moves the head off the branch it is on.
     * Keeps a client→server id swap from leaving a phantom sibling.
     */
    private evictOffBranchOptimisticMessages;
    switchToBranch(messageId: string): void;
    resetHead(messageId: string | null): void;
    clear(): void;
    export(): ExportedMessageRepository;
    import({ headId, messages }: ExportedMessageRepository): void;
}