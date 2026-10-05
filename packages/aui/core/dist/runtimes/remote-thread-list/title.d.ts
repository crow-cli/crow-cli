import { AssistantMessageStream } from "assistant-stream";
export declare const isTitleSourceMessage: (message: {
    status?: {
        type: string;
    } | undefined;
}) => boolean;
export declare const applyTitleStream: (stream: Parameters<typeof AssistantMessageStream.fromAssistantStream>[0], onTitle: (title: string | undefined) => Promise<void>) => Promise<void>;