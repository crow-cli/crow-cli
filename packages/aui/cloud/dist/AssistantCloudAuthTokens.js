import { readCloudRecord, readCloudString } from "./cloudResponse.js";
//#region src/AssistantCloudAuthTokens.ts
var AssistantCloudAuthTokens = class {
	cloud;
	constructor(cloud) {
		this.cloud = cloud;
	}
	async create() {
		const response = readCloudRecord(await this.cloud.makeRequest("/auth/tokens", { method: "POST" }), "auth token response");
		return { token: readCloudString(response.token, "token") };
	}
};
//#endregion
export { AssistantCloudAuthTokens };
