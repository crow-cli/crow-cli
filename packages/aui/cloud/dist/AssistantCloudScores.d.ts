import type { AssistantCloudAPI } from "./AssistantCloudAPI.js";
export type AssistantCloudScoreBody = {
    name: string;
    data_type: "numeric" | "categorical" | "boolean";
    value?: number | boolean;
    string_value?: string;
    comment?: string;
    thread_id?: string;
    message_id?: string;
    run_id?: string;
};
export type AssistantCloudScoreResponse = {
    score_id: string;
    name: string;
    data_type: "numeric" | "categorical" | "boolean";
    value: number | null;
    string_value: string | null;
};
export declare class AssistantCloudScores {
    private cloud;
    constructor(cloud: AssistantCloudAPI);
    create(body: AssistantCloudScoreBody): Promise<AssistantCloudScoreResponse>;
}