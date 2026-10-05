import type { ReadonlyJSONObject } from "assistant-stream/utils";
import type { AssistantCloudAPI } from "./AssistantCloudAPI.js";
export type CloudMessage = {
    id: string;
    parent_id: string | null;
    height: number;
    created_at: Date;
    updated_at: Date;
    format: "aui/v0" | string;
    content: ReadonlyJSONObject;
    external_id?: string | null | undefined;
};
type AssistantCloudThreadMessageListQuery = {
    format?: string;
    limit?: number;
    after?: string;
};
type AssistantCloudThreadMessageListResponse = {
    messages: CloudMessage[];
};
type AssistantCloudThreadMessageCreateBody = {
    parent_id: string | null;
    format: "aui/v0" | string;
    content: ReadonlyJSONObject;
    external_id?: string | undefined;
    parent_external_id?: string | undefined;
};
type AssistantCloudMessageCreateResponse = {
    message_id: string;
};
type AssistantCloudThreadMessageUpdateBody = {
    content: ReadonlyJSONObject;
};
export type AssistantCloudThreadMessageFeedbackBody = {
    type: "positive" | "negative";
    comment?: string;
};
export type AssistantCloudThreadMessageFeedbackResponse = {
    feedback_id: string;
    type: "positive" | "negative";
    comment?: string | null;
};
export declare const decodeCloudMessage: (value: unknown, field: string) => CloudMessage;
export declare class AssistantCloudThreadMessages {
    private cloud;
    constructor(cloud: AssistantCloudAPI);
    list(threadId: string, query?: AssistantCloudThreadMessageListQuery): Promise<AssistantCloudThreadMessageListResponse>;
    create(threadId: string, body: AssistantCloudThreadMessageCreateBody): Promise<AssistantCloudMessageCreateResponse>;
    update(threadId: string, messageId: string, body: AssistantCloudThreadMessageUpdateBody): Promise<void>;
    feedback(threadId: string, messageId: string, body: AssistantCloudThreadMessageFeedbackBody): Promise<AssistantCloudThreadMessageFeedbackResponse>;
}
export {};