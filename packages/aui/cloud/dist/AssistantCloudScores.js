import { readCloudEnum, readCloudNullableNumber, readCloudNullableString, readCloudRecord, readCloudString } from "./cloudResponse.js";
//#region src/AssistantCloudScores.ts
const SCORE_DATA_TYPES = [
	"numeric",
	"categorical",
	"boolean"
];
var AssistantCloudScores = class {
	cloud;
	constructor(cloud) {
		this.cloud = cloud;
	}
	async create(body) {
		const response = readCloudRecord(await this.cloud.makeRequest("/scores", {
			method: "POST",
			body
		}), "score response");
		return {
			score_id: readCloudString(response.score_id, "score response.score_id"),
			name: readCloudString(response.name, "score response.name"),
			data_type: readCloudEnum(response.data_type, "score response.data_type", SCORE_DATA_TYPES),
			value: readCloudNullableNumber(response.value, "score response.value"),
			string_value: readCloudNullableString(response.string_value, "score response.string_value")
		};
	}
};
//#endregion
export { AssistantCloudScores };
