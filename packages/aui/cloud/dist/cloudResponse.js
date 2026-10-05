//#region src/cloudResponse.ts
var CloudResponseError = class extends Error {
	constructor(message) {
		super(message);
		this.name = "CloudResponseError";
	}
};
const invalidCloudResponse = (field, expected) => new CloudResponseError(`Invalid Assistant Cloud response for "${field}": expected ${expected}`);
const readCloudRecord = (value, field) => {
	if (typeof value !== "object" || value === null || Array.isArray(value)) throw invalidCloudResponse(field, "an object");
	return value;
};
const readCloudArray = (value, field) => {
	if (!Array.isArray(value)) throw invalidCloudResponse(field, "an array");
	return value;
};
const readCloudString = (value, field) => {
	if (typeof value !== "string") throw invalidCloudResponse(field, "a string");
	return value;
};
const readCloudNumber = (value, field) => {
	if (typeof value !== "number" || !Number.isFinite(value)) throw invalidCloudResponse(field, "a number");
	return value;
};
const readCloudNullableNumber = (value, field) => {
	if (value === null) return null;
	return readCloudNumber(value, field);
};
const readCloudEnum = (value, field, allowed) => {
	const text = readCloudString(value, field);
	if (!allowed.includes(text)) throw invalidCloudResponse(field, `one of ${allowed.map((entry) => `"${entry}"`).join(", ")}`);
	return text;
};
const readCloudNullableString = (value, field) => {
	if (value === null) return null;
	return readCloudString(value, field);
};
const readCloudBoolean = (value, field) => {
	if (typeof value !== "boolean") throw invalidCloudResponse(field, "a boolean");
	return value;
};
const readCloudInteger = (value, field) => {
	if (!Number.isInteger(value)) throw invalidCloudResponse(field, "an integer");
	return value;
};
const readCloudTimestamp = (value, field) => {
	if (typeof value !== "string") throw invalidCloudResponse(field, "a canonical ISO timestamp");
	const date = new Date(value);
	if (Number.isNaN(date.getTime()) || date.toISOString() !== value) throw invalidCloudResponse(field, "a canonical ISO timestamp");
	return date;
};
const readCloudJSONObject = (value, field) => readCloudRecord(value, field);
//#endregion
export { CloudResponseError, readCloudArray, readCloudBoolean, readCloudEnum, readCloudInteger, readCloudJSONObject, readCloudNullableNumber, readCloudNullableString, readCloudNumber, readCloudRecord, readCloudString, readCloudTimestamp };
