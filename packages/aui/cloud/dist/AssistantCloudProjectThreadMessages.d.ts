import type { AssistantCloudAPI } from "./AssistantCloudAPI.js";
import { type CloudMessage } from "./AssistantCloudThreadMessages.js";
type AssistantCloudProjectThreadMessageListQuery = {
    format?: string;
    limit?: number;
    after?: string;
};
type AssistantCloudProjectThreadMessageListResponse = {
    messages: CloudMessage[];
};
export declare class AssistantCloudProjectThreadMessages {
    private cloud;
    constructor(cloud: AssistantCloudAPI);
    list(threadId: string, query?: AssistantCloudProjectThreadMessageListQuery): Promise<AssistantCloudProjectThreadMessageListResponse>;
}
export {};