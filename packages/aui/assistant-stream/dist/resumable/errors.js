//#region src/resumable/errors.ts
var ResumableStreamError = class extends Error {
	code;
	constructor(code, message) {
		super(message);
		this.name = "ResumableStreamError";
		this.code = code;
	}
};
const STREAM_ID_PATTERN = /^[A-Za-z0-9_.:-]{1,256}$/;
function validateStreamId(streamId) {
	if (!STREAM_ID_PATTERN.test(streamId)) throw new ResumableStreamError("invalid-id", `Invalid streamId: ${streamId} (must match ${STREAM_ID_PATTERN})`);
}
//#endregion
export { ResumableStreamError, validateStreamId };
