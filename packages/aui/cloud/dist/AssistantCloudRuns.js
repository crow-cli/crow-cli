import { CloudResponseError, readCloudRecord, readCloudString } from "./cloudResponse.js";
import { AssistantStream, PlainTextDecoder } from "assistant-stream";
//#region src/AssistantCloudRuns.ts
var AssistantCloudRuns = class {
	cloud;
	constructor(cloud) {
		this.cloud = cloud;
	}
	__internal_getAssistantOptions(assistantId) {
		return {
			api: `${this.cloud._baseUrl}/v1/runs/stream`,
			protocol: "ui-message-stream",
			headers: async () => {
				const headers = await this.cloud._auth.getAuthHeaders();
				if (!headers) throw new Error("Authorization failed");
				return {
					...headers,
					Accept: "text/plain",
					"Aui-Sdk": this.cloud.sdkHeader()
				};
			},
			body: async (options) => {
				const threadId = options?.threadId;
				if (threadId === void 0) throw new Error("Assistant Cloud runs need a thread; the thread list adapter has not assigned a remote id to this thread yet.");
				return {
					assistant_id: assistantId,
					response_format: "vercel-ai-data-stream/v1",
					thread_id: threadId
				};
			}
		};
	}
	async stream(body) {
		const response = await this.cloud.makeRawRequest("/runs/stream", {
			method: "POST",
			headers: { Accept: "text/plain" },
			body
		});
		if (!response.body) throw new CloudResponseError("Invalid Assistant Cloud response for \"run stream\": expected a response body");
		const receivedContentType = response.headers.get("content-type");
		if (receivedContentType?.split(";", 1)[0]?.trim().toLowerCase() !== "text/plain") {
			await response.body.cancel().catch(() => void 0);
			throw new CloudResponseError(`Invalid Assistant Cloud response for "run stream": expected a "text/plain" content type, received ${receivedContentType ? `"${receivedContentType}"` : "no Content-Type header"}`);
		}
		return AssistantStream.fromResponse(response, new PlainTextDecoder());
	}
	async report(body) {
		const response = readCloudRecord(await this.cloud.makeRequest("/runs", {
			method: "POST",
			body
		}), "run report response");
		return { run_id: readCloudString(response.run_id, "run_id") };
	}
};
//#endregion
export { AssistantCloudRuns };
