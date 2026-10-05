import { AssistantCloudProjectThreads } from "./AssistantCloudProjectThreads.js";
//#region src/AssistantCloudProjects.ts
var AssistantCloudProjects = class {
	threads;
	constructor(cloud) {
		this.threads = new AssistantCloudProjectThreads(cloud);
	}
};
//#endregion
export { AssistantCloudProjects };
