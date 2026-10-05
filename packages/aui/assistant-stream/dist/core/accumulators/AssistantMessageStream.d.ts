import type { AssistantStream } from "../AssistantStream.js";
import type { AssistantMessage } from "../utils/types.js";
export declare class AssistantMessageStream {
    readonly readable: ReadableStream<AssistantMessage>;
    constructor(readable: ReadableStream<AssistantMessage>);
    static fromAssistantStream(stream: AssistantStream): AssistantMessageStream;
    unstable_result(): Promise<AssistantMessage>;
    [Symbol.asyncIterator](): AsyncIterator<AssistantMessage, any, any>;
    tee(): [AssistantMessageStream, AssistantMessageStream];
}