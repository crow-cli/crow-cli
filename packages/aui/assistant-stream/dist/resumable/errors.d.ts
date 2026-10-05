export type ResumableStreamErrorCode = "missing" | "exists" | "finalized" | "invalid-id";
export declare class ResumableStreamError extends Error {
    readonly code: ResumableStreamErrorCode;
    constructor(code: ResumableStreamErrorCode, message: string);
}
export declare function validateStreamId(streamId: string): void;