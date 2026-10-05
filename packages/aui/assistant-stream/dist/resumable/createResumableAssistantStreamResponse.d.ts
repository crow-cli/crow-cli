import type { AssistantStreamEncoder } from "../core/AssistantStream.js";
import { type AssistantStreamController } from "../core/modules/assistant-stream.js";
import type { ResumableStreamContext } from "./ResumableStreamContext.js";
export declare const RESUMABLE_STREAM_ID_HEADER = "x-resumable-stream-id";
export type CreateResumableAssistantStreamResponseOptions = {
    readonly context: ResumableStreamContext;
    readonly streamId: string;
    readonly callback: (controller: AssistantStreamController) => PromiseLike<void> | void;
    /** Defaults to `DataStreamEncoder`. Also consulted for response headers. */
    readonly encoder?: () => AssistantStreamEncoder;
    readonly headers?: HeadersInit;
};
export declare function createResumableAssistantStreamResponse(options: CreateResumableAssistantStreamResponseOptions): Promise<Response>;
export type CreateResumeAssistantStreamResponseOptions = {
    readonly context: ResumableStreamContext;
    readonly streamId: string;
    /** Read for `headers` only; the encoder transform is not invoked on resume. */
    readonly encoder?: () => AssistantStreamEncoder;
    readonly headers?: HeadersInit;
    /** Defaults to a 404 JSON response. */
    readonly missingResponse?: () => Response;
};
export declare function createResumeAssistantStreamResponse(options: CreateResumeAssistantStreamResponseOptions): Promise<Response>;