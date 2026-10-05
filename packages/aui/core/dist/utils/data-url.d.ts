export declare const httpUrlPattern: RegExp;
export type FilePartSource = {
    kind: "url";
    url: string;
} | {
    kind: "data";
    data: string;
    mimeType: string;
};
export declare function parseDataUrl(value: string): {
    mimeType: string;
    data: string;
} | null;
export declare const resolveFilePartSource: (part: {
    data: string;
    mimeType: string;
    sourceType?: string | undefined;
}) => FilePartSource;
/**
 * Whether a payload is something `new URL()` accepts. Adapters that place a
 * `FileMessagePart` payload into a url-typed wire field use this to decide
 * whether it has to be wrapped in a data URL envelope first; base64 cannot
 * contain a colon, so a real payload is never misread as a url.
 */
export declare function isParsableUrl(value: string): boolean;
/**
 * The media type a data URL declares, whether or not its payload is base64.
 * `parseDataUrl` only matches base64 payloads because it also returns the
 * bytes; this reads the declaration alone.
 */
export declare function dataUrlMediaType(value: string): string | undefined;