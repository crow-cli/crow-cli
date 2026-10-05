import type { ThreadMessage } from "../../types/message.js";
import { MessageRepository, type ExportedMessageRepository } from "./message-repository.js";
export type MessageRepositorySessionOptions = {
    decorateExport?: (exported: ExportedMessageRepository, repository: MessageRepository) => ExportedMessageRepository;
};
export declare const createMessageRepositorySession: (options?: MessageRepositorySessionOptions) => {
    getMessages: () => readonly ThreadMessage[];
    readonly headId: string | null;
    export: () => ExportedMessageRepository;
    tryGetMessage: (messageId: string) => {
        parentId: string | null;
        message: ThreadMessage;
        index: number;
    } | undefined;
    tryGetMessages: (messageId: string) => readonly ThreadMessage[] | undefined;
    hasMessage: (messageId: string) => boolean;
    addOrUpdateMessage: (parentId: string | null, message: ThreadMessage) => void;
    deleteMessage: (messageId: string, replacementId?: string | null) => void;
    tryDeleteMessage: (messageId: string) => boolean;
    switchToBranch: (messageId: string) => void;
    resetHead: (messageId: string | null) => void;
    clear: () => void;
    updateMessage: (messageId: string, updater: (message: ThreadMessage) => ThreadMessage) => boolean;
    applyExternalMessageRepository: (loaded: ExportedMessageRepository) => void;
};
export type MessageRepositorySession = ReturnType<typeof createMessageRepositorySession>;