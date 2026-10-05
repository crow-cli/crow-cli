import { AssistantCloudAPI } from "./AssistantCloudAPI.js";
import { AssistantCloudAuthTokens } from "./AssistantCloudAuthTokens.js";
import { AssistantCloudThreads } from "./AssistantCloudThreads.js";
import { AssistantCloudProjects } from "./AssistantCloudProjects.js";
import { AssistantCloudRuns } from "./AssistantCloudRuns.js";
import { AssistantCloudFiles } from "./AssistantCloudFiles.js";
import { AssistantCloudEvents, clearPendingAssistantCloudEvents } from "./AssistantCloudEvents.js";
import { AssistantCloudScores } from "./AssistantCloudScores.js";
//#region src/AssistantCloud.ts
var AssistantCloud = class {
	threads;
	projects;
	auth;
	runs;
	files;
	events;
	scores;
	telemetry;
	registerSdk;
	constructor(config) {
		const api = new AssistantCloudAPI(config);
		this.registerSdk = api.registerSdk;
		const t = config.telemetry;
		const telemetry = t === false ? { enabled: false } : t === true || t === void 0 ? { enabled: true } : {
			...t,
			enabled: t.enabled !== false
		};
		this.telemetry = new Proxy(telemetry, { set: (target, property, value) => {
			const updated = Reflect.set(target, property, value);
			if ((property === "enabled" || property === "events") && (target.enabled === false || target.events === false)) clearPendingAssistantCloudEvents(this.events);
			return updated;
		} });
		this.threads = new AssistantCloudThreads(api);
		this.projects = new AssistantCloudProjects(api);
		this.auth = { tokens: new AssistantCloudAuthTokens(api) };
		this.runs = new AssistantCloudRuns(api);
		this.files = new AssistantCloudFiles(api);
		this.events = new AssistantCloudEvents(api, () => this.telemetry.enabled !== false && this.telemetry.events !== false);
		this.scores = new AssistantCloudScores(api);
	}
};
//#endregion
export { AssistantCloud };
