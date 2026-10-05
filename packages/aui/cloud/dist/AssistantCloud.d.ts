import { type AssistantCloudConfig, type SdkIdentity, type AssistantCloudTelemetryConfig } from "./AssistantCloudAPI.js";
import { AssistantCloudAuthTokens } from "./AssistantCloudAuthTokens.js";
import { AssistantCloudProjects } from "./AssistantCloudProjects.js";
import { AssistantCloudRuns } from "./AssistantCloudRuns.js";
import { AssistantCloudThreads } from "./AssistantCloudThreads.js";
import { AssistantCloudFiles } from "./AssistantCloudFiles.js";
import { AssistantCloudEvents } from "./AssistantCloudEvents.js";
import { AssistantCloudScores } from "./AssistantCloudScores.js";
export declare class AssistantCloud {
    readonly threads: AssistantCloudThreads;
    readonly projects: AssistantCloudProjects;
    readonly auth: {
        tokens: AssistantCloudAuthTokens;
    };
    readonly runs: AssistantCloudRuns;
    readonly files: AssistantCloudFiles;
    readonly events: AssistantCloudEvents;
    readonly scores: AssistantCloudScores;
    readonly telemetry: AssistantCloudTelemetryConfig;
    readonly registerSdk: (sdk: SdkIdentity) => void;
    constructor(config: AssistantCloudConfig);
}