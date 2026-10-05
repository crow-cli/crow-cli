//#region src/utils/image-media-type.ts
/**
* Leading-byte signatures for the image formats a browser or attachment
* adapter realistically produces. `null` matches any byte, which WebP needs
* because its four size bytes sit between the two markers, and AVIF and HEIC
* need because their leading `ftyp` box size varies by encoder.
*
* These are file format constants rather than an evolving API, so the table
* mirrors the one the AI SDK applies on the far side of several adapters
* without taking a dependency to reach it.
*/
const IMAGE_SIGNATURES = [
	{
		mediaType: "image/gif",
		prefix: [
			71,
			73,
			70
		]
	},
	{
		mediaType: "image/png",
		prefix: [
			137,
			80,
			78,
			71
		]
	},
	{
		mediaType: "image/jpeg",
		prefix: [255, 216]
	},
	{
		mediaType: "image/webp",
		prefix: [
			82,
			73,
			70,
			70,
			null,
			null,
			null,
			null,
			87,
			69,
			66,
			80
		]
	},
	{
		mediaType: "image/bmp",
		prefix: [66, 77]
	},
	{
		mediaType: "image/tiff",
		prefix: [
			73,
			73,
			42,
			0
		]
	},
	{
		mediaType: "image/tiff",
		prefix: [
			77,
			77,
			0,
			42
		]
	},
	{
		mediaType: "image/avif",
		prefix: [
			null,
			null,
			null,
			null,
			102,
			116,
			121,
			112,
			97,
			118,
			105,
			102
		]
	},
	{
		mediaType: "image/heic",
		prefix: [
			null,
			null,
			null,
			null,
			102,
			116,
			121,
			112,
			104,
			101,
			105,
			99
		]
	}
];
/** 16 base64 characters decode to the 12 bytes the longest signature needs. */
const PREFIX_CHARS = 16;
const decodePrefix = (base64) => {
	const prefix = base64.slice(0, PREFIX_CHARS);
	const aligned = prefix.slice(0, prefix.length - prefix.length % 4);
	if (aligned.length === 0) return void 0;
	const nodeBuffer = globalThis.Buffer;
	if (nodeBuffer) return new Uint8Array(nodeBuffer.from(aligned, "base64"));
	try {
		const binary = atob(aligned);
		const bytes = new Uint8Array(binary.length);
		for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
		return bytes;
	} catch {
		return;
	}
};
/**
* The image media type a base64 payload's leading bytes identify, or
* `undefined` when they match no known signature or the input is not base64.
*
* An `ImageMessagePart` carries no media type, so an adapter that must declare
* one on the wire reads it from the bytes rather than assuming a format. Never
* throws: the input is whatever a caller put on the part.
*/
function detectImageMediaType(base64) {
	const bytes = decodePrefix(base64);
	if (!bytes) return void 0;
	return IMAGE_SIGNATURES.find(({ prefix }) => bytes.length >= prefix.length && prefix.every((byte, index) => byte === null || bytes[index] === byte))?.mediaType;
}
//#endregion
export { detectImageMediaType };
