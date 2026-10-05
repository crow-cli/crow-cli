import { readCloudArray, readCloudBoolean, readCloudRecord, readCloudString } from "./cloudResponse.js";
//#region src/AssistantCloudFiles.ts
var AssistantCloudFiles = class {
	cloud;
	constructor(cloud) {
		this.cloud = cloud;
	}
	/**
	* @deprecated Assistant Cloud has no PDF conversion endpoint, so this request always rejects with a `CloudAPIError` whose `status` is 404.
	*/
	async pdfToImages(body) {
		const response = readCloudRecord(await this.cloud.makeRequest("/files/pdf-to-images", {
			method: "POST",
			body
		}), "PDF conversion response");
		return {
			success: readCloudBoolean(response.success, "PDF conversion response.success"),
			urls: readCloudArray(response.urls, "PDF conversion response.urls").map((url, index) => readCloudString(url, `PDF conversion response.urls[${index}]`)),
			message: readCloudString(response.message, "PDF conversion response.message")
		};
	}
	async generatePresignedUploadUrl(body) {
		const response = readCloudRecord(await this.cloud.makeRequest("/files/attachments/generate-presigned-upload-url", {
			method: "POST",
			body
		}), "presigned upload response");
		return {
			success: readCloudBoolean(response.success, "presigned upload response.success"),
			signedUrl: readCloudString(response.signedUrl, "presigned upload response.signedUrl"),
			expiresAt: readCloudString(response.expiresAt, "presigned upload response.expiresAt"),
			publicUrl: readCloudString(response.publicUrl, "presigned upload response.publicUrl"),
			..."key" in response ? { key: readCloudString(response.key, "presigned upload response.key") } : {}
		};
	}
	async generatePresignedDownloadUrl(body) {
		const response = readCloudRecord(await this.cloud.makeRequest("/files/attachments/generate-presigned-download-url", {
			method: "POST",
			body
		}), "presigned download response");
		return {
			signedUrl: readCloudString(response.signedUrl, "presigned download response.signedUrl"),
			expiresAt: readCloudString(response.expiresAt, "presigned download response.expiresAt"),
			key: readCloudString(response.key, "presigned download response.key")
		};
	}
};
//#endregion
export { AssistantCloudFiles };
