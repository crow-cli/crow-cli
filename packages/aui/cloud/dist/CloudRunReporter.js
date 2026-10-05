import { CloudAPIError } from "./AssistantCloudAPI.js";
import { createRunReport } from "./runTelemetry.js";
//#region src/CloudRunReporter.ts
/**
* Sends run reports the way every client integration has to: nothing while
* telemetry is off, the cloud's environment, release and tags on every report,
* the `beforeReport` hook applied last, and a failed send that never surfaces.
* A keyed report is deduplicated while in flight and after an attempt. A
* rate-limited attempt releases the key so a later observation can try again.
*/
var CloudRunReporter = class {
	reported = /* @__PURE__ */ new Set();
	getCloud;
	constructor(cloud) {
		this.getCloud = typeof cloud === "function" ? cloud : () => cloud;
	}
	async report(init, key) {
		let claimedKey;
		try {
			const cloud = this.getCloud();
			if (!cloud.telemetry.enabled) return;
			if (key !== void 0 && this.reported.has(key)) return;
			const initial = createRunReport({
				...init,
				telemetry: cloud.telemetry
			});
			const { beforeReport } = cloud.telemetry;
			const report = beforeReport ? beforeReport(initial) : initial;
			if (!report) return;
			if (key !== void 0) {
				this.reported.add(key);
				claimedKey = key;
			}
			await cloud.runs.report(report);
		} catch (error) {
			if (claimedKey !== void 0 && isRetryableReportError(error)) this.reported.delete(claimedKey);
			return;
		}
	}
};
const isRetryableReportError = (error) => {
	return error instanceof CloudAPIError && error.status === 429;
};
//#endregion
export { CloudRunReporter };
