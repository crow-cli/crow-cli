import type { AssistantCloudAPI } from "./AssistantCloudAPI.js";
import { AssistantCloudProjectThreads } from "./AssistantCloudProjectThreads.js";
export declare class AssistantCloudProjects {
    readonly threads: AssistantCloudProjectThreads;
    constructor(cloud: AssistantCloudAPI);
}