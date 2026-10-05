import type { AssistantCloudAPI } from "./AssistantCloudAPI.js";
import { AssistantCloudThreadMessages } from "./AssistantCloudThreadMessages.js";
type AssistantCloudThreadsListQuery = {
    is_archived?: boolean;
    limit?: number;
    after?: string;
};
export type CloudThread = {
    title: string;
    last_message_at: Date;
    metadata: unknown;
    external_id: string | null;
    id: string;
    project_id: string;
    created_at: Date;
    updated_at: Date;
    workspace_id: string;
    is_archived: boolean;
};
type AssistantCloudThreadsListResponse = {
    threads: CloudThread[];
};
type AssistantCloudThreadsCreateBody = {
    title?: string | undefined;
    last_message_at: Date;
    metadata?: unknown | undefined;
    external_id?: string | undefined;
    upsert?: boolean | undefined;
};
type AssistantCloudThreadsCreateResponse = {
    thread_id: string;
};
type AssistantCloudThreadsClaimBody = {
    refresh_token: string;
};
type AssistantCloudThreadsClaimResponse = {
    moved: number;
};
type AssistantCloudThreadsUpdateBody = {
    title?: string | undefined;
    last_message_at?: Date | undefined;
    metadata?: unknown | undefined;
    is_archived?: boolean | undefined;
};
export declare const decodeCloudThread: (value: unknown, field: string) => CloudThread;
export declare class AssistantCloudThreads {
    readonly messages: AssistantCloudThreadMessages;
    private cloud;
    constructor(cloud: AssistantCloudAPI);
    list(query?: AssistantCloudThreadsListQuery): Promise<AssistantCloudThreadsListResponse>;
    get(threadId: string): Promise<CloudThread>;
    create(body: AssistantCloudThreadsCreateBody): Promise<AssistantCloudThreadsCreateResponse>;
    update(threadId: string, body: AssistantCloudThreadsUpdateBody): Promise<void>;
    /** Moves every thread of the anonymous identity behind `refresh_token` into the caller's workspace. */
    claim(body: AssistantCloudThreadsClaimBody): Promise<AssistantCloudThreadsClaimResponse>;
    delete(threadId: string): Promise<void>;
}
export {};