/**
 * The media type to declare for an `ImageMessagePart`, which carries none of
 * its own: an attachment's content type, then the payload's data URL
 * declaration, then its leading bytes, then `image/png`.
 *
 * The floor cannot be a wildcard. `image/*` is rejected outright by the AI SDK
 * for a url source and whenever inline bytes fail to sniff, so it fails exactly
 * where a fallback is needed.
 */
export declare function resolveImageMediaType(image: string, contentType?: string | undefined): string;
/**
 * The media type to declare for a `FileMessagePart`: its own `mimeType`, then
 * the payload's data URL declaration, then `application/octet-stream`.
 *
 * `mimeType` is a plain string, and an adapter reading `file.type` on a file
 * the OS cannot type yields `""`, so the declared value is not always present.
 */
export declare function resolveFileMediaType(data: string, mimeType?: string | undefined): string;
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
export declare function toMediaWireUrl(payload: string, mediaType: string): string;