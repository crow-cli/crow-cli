import type { ReadonlyJSONObject } from "assistant-stream/utils";
import type { AssistantCloud } from "./AssistantCloud.js";
import type { CloudMessage } from "./AssistantCloudThreadMessages.js";
/**
 * Appends, updates and loads cloud messages while mapping local ids to cloud
 * ids and chaining parent_id. A parent that is still being created is awaited,
 * so concurrent appends land under the right parent.
 */
export declare class CloudMessagePersistence {
    private idMapping;
    private getCloud;
    constructor(cloud: AssistantCloud);
    constructor(getCloud: () => AssistantCloud);
    /**
     * Persist a message to the cloud.
     *
     * @param threadId - Remote thread ID
     * @param messageId - Local message ID (used for tracking)
     * @param parentId - Local parent message ID (or null for first message)
     * @param format - Message format (e.g., "aui/v0", "ai-sdk/v6")
     * @param content - Message content (format-specific)
     */
    append(threadId: string, messageId: string, parentId: string | null, format: string, content: ReadonlyJSONObject): Promise<void>;
    /**
     * Update an already-persisted message in the cloud.
     */
    update(threadId: string, messageId: string, _format: string, content: ReadonlyJSONObject): Promise<void>;
    /**
     * Check if a message has been persisted (or is currently being persisted).
     */
    isPersisted(messageId: string): boolean;
    /**
     * Get the remote ID for a local message ID (resolved).
     * Returns undefined if not persisted.
     */
    getRemoteId(messageId: string): Promise<string | undefined>;
    getResolvedRemoteId(messageId: string): string | undefined;
    record(localId: string, remoteId: string): void;
    /**
     * Load messages from the cloud and populate the ID mapping.
     *
     * The list endpoint caps a response at 200 rows, so pages are followed by
     * message ID cursor until a short page and concatenated in server order.
     *
     * The ID mapping is populated so that `isPersisted()` returns true for
     * loaded messages, preventing re-persistence of already-stored messages.
     *
     * A loaded ID that an append already maps keeps the remote ID from that append, and falls back to the loaded ID if the append fails.
     *
     * @param threadId - Remote thread ID
     * @param format - Optional format filter
     * @returns Array of cloud messages
     */
    load(threadId: string, format?: string): Promise<CloudMessage[]>;
    /**
     * Reset the ID mapping (call when switching threads).
     *
     * Pending `load()` and `append()` calls are not cancelled and still settle
     * normally, but their results no longer populate the ID mapping.
     */
    reset(): void;
}