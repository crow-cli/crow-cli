import type { AssistantCloudAPI } from "./AssistantCloudAPI.js";
type AssistantCloudAuthTokensCreateResponse = {
    token: string;
};
export declare class AssistantCloudAuthTokens {
    private cloud;
    constructor(cloud: AssistantCloudAPI);
    create(): Promise<AssistantCloudAuthTokensCreateResponse>;
}
export {};