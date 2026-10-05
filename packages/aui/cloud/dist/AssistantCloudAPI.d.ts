import { type AssistantCloudAuthStrategy } from "./AssistantCloudAuthStrategy.js";
import type { AssistantCloudRunReport } from "./AssistantCloudRuns.js";
export type SdkIdentity = {
    name: string;
    version: string;
};
export type AssistantCloudTelemetryConfig = {
    /**
     * Enables Assistant Cloud telemetry. Defaults to `true`. Set to `false` to
     * disable both run reports and engagement events.
     */
    enabled?: boolean;
    /**
     * Enables Assistant Cloud engagement events. Defaults to `true` when
     * telemetry is enabled. Set to `false` to keep run reports while disabling
     * engagement events.
     */
    events?: boolean;
    /**
     * Stores the messages of runtimes whose backend keeps the transcript (LangGraph, LangChain, Google ADK, custom external stores), so the dashboard can show them. Defaults to `true` when telemetry is enabled. Set to `false` to keep run reports and events without storing those messages.
     */
    messages?: boolean;
    release?: string;
    environment?: string;
    tags?: string[];
    /**
     * Called before each telemetry report is sent.
     * Return a modified report to enrich it (e.g. add `model_id`),
     * or return `null` to skip the report.
     */
    beforeReport?: (report: AssistantCloudRunReport) => AssistantCloudRunReport | null;
};
export type AssistantCloudConfig = ({
    baseUrl: string;
    authToken: () => Promise<string | null>;
} | {
    baseUrl?: string;
    apiKey: string;
    userId: string;
    workspaceId: string;
} | {
    baseUrl: string;
    anonymous: true;
}) & {
    /**
     * Client-side run telemetry reporting. Default: `true`.
     *
     * When enabled, the SDK automatically reports run metadata (status, step
     * count, tool calls, and token usage) to Assistant Cloud after each
     * assistant message is saved. Reports can also include assistant output,
     * tool arguments and results, errors, and metadata, which may contain
     * sensitive content. Use `beforeReport` to redact or drop reports, or
     * `telemetry: false` to disable reporting.
     *
     * - `true` / `undefined` — enabled with defaults
     * - `false` — disabled
     * - `{ beforeReport }` — enabled with a hook to enrich or filter reports
     */
    telemetry?: boolean | AssistantCloudTelemetryConfig;
};
export declare class CloudAPIError extends Error {
    readonly status: number;
    readonly code?: string;
    readonly details?: Record<string, unknown>;
    constructor(message: string, status: number, code?: string, details?: Record<string, unknown>);
}
type MakeRequestOptions = {
    method?: "POST" | "PUT" | "DELETE" | undefined;
    headers?: Record<string, string> | undefined;
    query?: Record<string, string | number | boolean> | undefined;
    body?: object | undefined;
    keepalive?: boolean | undefined;
};
export declare class AssistantCloudAPI {
    _auth: AssistantCloudAuthStrategy;
    _baseUrl: string;
    readonly registerSdk: (sdk: SdkIdentity) => void;
    readonly sdkHeader: () => string;
    constructor(config: AssistantCloudConfig);
    initializeAuth(): Promise<boolean>;
    makeRawRequest(endpoint: string, options?: MakeRequestOptions): Promise<Response>;
    makeRequest(endpoint: string, options?: MakeRequestOptions): Promise<any>;
}
export {};