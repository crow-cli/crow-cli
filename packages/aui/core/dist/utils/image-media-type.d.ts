/**
 * The image media type a base64 payload's leading bytes identify, or
 * `undefined` when they match no known signature or the input is not base64.
 *
 * An `ImageMessagePart` carries no media type, so an adapter that must declare
 * one on the wire reads it from the bytes rather than assuming a format. Never
 * throws: the input is whatever a caller put on the part.
 */
export declare function detectImageMediaType(base64: string): string | undefined;