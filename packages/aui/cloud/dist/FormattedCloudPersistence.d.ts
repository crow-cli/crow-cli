import type { ReadonlyJSONObject } from "assistant-stream/utils";
/**
 * Format adapter shape — structurally identical to the MessageFormatAdapter
 * in @assistant-ui/react, but defined here to avoid cross-package type moves.
 * TypeScript's structural typing ensures these are interchangeable.
 */
export type MessageFormatAdapter<TMessage, TStorageFormat> = {
    format: string;
    encode(item: {
        parentId: string | null;
        message: TMessage;
    }): TStorageFormat;
    decode(stored: {
        id: string;
        parent_id: string | null;
        format: string;
        content: TStorageFormat;
    }): {
        parentId: string | null;
        message: TMessage;
    };
    getId(message: TMessage): string;
};
/**
 * Wraps a CloudMessagePersistence with a MessageFormatAdapter's encode and
 * decode. The persistence parameter is typed structurally, so a caller does
 * not need to import the class.
 */
export declare const createFormattedPersistence: <TMessage, TStorageFormat>(persistence: {
    append: (threadId: string, messageId: string, parentId: string | null, format: string, content: ReadonlyJSONObject) => Promise<void>;
    load: (threadId: string, format?: string) => Promise<any[]>;
    isPersisted: (messageId: string) => boolean;
    update?: (threadId: string, messageId: string, format: string, content: ReadonlyJSONObject) => Promise<void>;
}, adapter: MessageFormatAdapter<TMessage, TStorageFormat>) => {
    append: (threadId: string, item: {
        parentId: string | null;
        message: TMessage;
    }) => Promise<void>;
    update: ((threadId: string, item: {
        parentId: string | null;
        message: TMessage;
    }, messageId: string) => Promise<void>) | undefined;
    load: (threadId: string) => Promise<{
        messages: {
            parentId: string | null;
            message: TMessage;
        }[];
    }>;
    isPersisted: (messageId: string) => boolean;
};