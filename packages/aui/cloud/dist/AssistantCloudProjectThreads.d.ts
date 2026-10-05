import type { AssistantCloudAPI } from "./AssistantCloudAPI.js";
import { AssistantCloudProjectThreadMessages } from "./AssistantCloudProjectThreadMessages.js";
import { type CloudThread } from "./AssistantCloudThreads.js";
type AssistantCloudProjectThreadsListQuery = {
    is_archived?: boolean;
    limit?: number;
    after?: string;
};
type AssistantCloudProjectThreadsListResponse = {
    threads: CloudThread[];
};
export declare class AssistantCloudProjectThreads {
    readonly messages: AssistantCloudProjectThreadMessages;
    private cloud;
    constructor(cloud: AssistantCloudAPI);
    list(query?: AssistantCloudProjectThreadsListQuery): Promise<AssistantCloudProjectThreadsListResponse>;
}
export {};