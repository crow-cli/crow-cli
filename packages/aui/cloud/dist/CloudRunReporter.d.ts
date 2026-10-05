import type { AssistantCloud } from "./AssistantCloud.js";
import { type RunReportInit } from "./runTelemetry.js";
export type CloudRunReportInit = Omit<RunReportInit, "telemetry">;
/**
 * Sends run reports the way every client integration has to: nothing while
 * telemetry is off, the cloud's environment, release and tags on every report,
 * the `beforeReport` hook applied last, and a failed send that never surfaces.
 * A keyed report is deduplicated while in flight and after an attempt. A
 * rate-limited attempt releases the key so a later observation can try again.
 */
export declare class CloudRunReporter {
    private readonly reported;
    private readonly getCloud;
    constructor(cloud: AssistantCloud | (() => AssistantCloud));
    report(init: CloudRunReportInit, key?: string): Promise<void>;
}