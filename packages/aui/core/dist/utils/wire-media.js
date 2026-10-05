import { dataUrlMediaType, isParsableUrl, parseDataUrl } from "./data-url.js";
import { detectImageMediaType } from "./image-media-type.js";
//#region src/utils/wire-media.ts
/**
* The media type to declare for an `ImageMessagePart`, which carries none of
* its own: an attachment's content type, then the payload's data URL
* declaration, then its leading bytes, then `image/png`.
*
* The floor cannot be a wildcard. `image/*` is rejected outright by the AI SDK
* for a url source and whenever inline bytes fail to sniff, so it fails exactly
* where a fallback is needed.
*/
function resolveImageMediaType(image, contentType) {
	if (contentType?.startsWith("image/") && !contentType.includes("*")) return contentType;
	const declared = dataUrlMediaType(image);
	if (declared?.startsWith("image/") && !declared.includes("*")) return declared;
	const payload = parseDataUrl(image)?.data ?? (isParsableUrl(image) ? void 0 : image);
	if (payload !== void 0) {
		const sniffed = detectImageMediaType(payload);
		if (sniffed) return sniffed;
	}
	return "image/png";
}
/**
* The media type to declare for a `FileMessagePart`: its own `mimeType`, then
* the payload's data URL declaration, then `application/octet-stream`.
*
* `mimeType` is a plain string, and an adapter reading `file.type` on a file
* the OS cannot type yields `""`, so the declared value is not always present.
*/
function resolveFileMediaType(data, mimeType) {
	return mimeType || dataUrlMediaType(data) || "application/octet-stream";
}
/**
* A payload placed into a wire field that is contractually a url.
*
* Two hazards drive this. A consumer may hand the value to an unguarded
* `new URL()`, so a payload that is not a url has to be wrapped; and a data
* URL's own media type wins over a separately declared one downstream, so a
* base64 envelope that disagrees with `mediaType` is rebuilt around the same
* bytes. Everything else passes through byte for byte: an envelope that agrees,
* a url of any other scheme, and a percent-encoded data URL, whose declaration
* cannot be corrected without transcoding the payload and is authoritative for
* the bytes it carries anyway.
*/
function toMediaWireUrl(payload, mediaType) {
	const parsed = parseDataUrl(payload);
	if (parsed) return parsed.mimeType === mediaType ? payload : `data:${mediaType};base64,${parsed.data}`;
	if (isParsableUrl(payload)) return payload;
	return `data:${mediaType};base64,${payload}`;
}
//#endregion
export { resolveFileMediaType, resolveImageMediaType, toMediaWireUrl };
