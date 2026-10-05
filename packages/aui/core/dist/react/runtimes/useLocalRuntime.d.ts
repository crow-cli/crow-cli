import type { AssistantRuntime, ChatModelAdapter, ThreadMessageLike } from "../../index.js";
import type { LocalRuntimeOptionsBase } from "../../runtimes/local/local-runtime-options.js";
import type { AssistantCloud } from "assistant-cloud";
export type LocalRuntimeOptions = Omit<LocalRuntimeOptionsBase, "adapters"> & {
    cloud?: AssistantCloud | undefined;
    initialMessages?: readonly ThreadMessageLike[] | undefined;
    adapters?: Omit<LocalRuntimeOptionsBase["adapters"], "chatModel"> | undefined;
};
export declare const splitLocalRuntimeOptions: <T extends LocalRuntimeOptions>(options: T) => {
    localRuntimeOptions: {
        cloud: AssistantCloud | undefined;
        initialMessages: readonly ThreadMessageLike[] | undefined;
        maxSteps: number | undefined;
        adapters: Omit<{
            chatModel: ChatModelAdapter;
            history?: import("../../adapters/index.js").ThreadHistoryAdapter | undefined;
            attachments?: import("../../adapters/index.js").AttachmentAdapter | undefined;
            speech?: import("../../adapters/index.js").SpeechSynthesisAdapter | undefined;
            dictation?: import("../../adapters/index.js").DictationAdapter | undefined;
            voice?: import("../../adapters/index.js").RealtimeVoiceAdapter | undefined;
            feedback?: import("../../adapters/index.js").FeedbackAdapter | undefined;
            suggestion?: import("../../adapters/index.js").SuggestionAdapter | undefined;
        }, "chatModel"> | undefined;
        unstable_humanToolNames: string[] | undefined;
        unstable_enableMessageQueue: boolean | undefined;
        unstable_queueClearOnRewind: boolean | undefined;
        unstable_queueClearOnCancel: boolean | undefined;
    };
    otherOptions: Omit<T, "adapters" | "cloud" | "maxSteps" | "unstable_humanToolNames" | "unstable_enableMessageQueue" | "unstable_queueClearOnRewind" | "unstable_queueClearOnCancel" | "initialMessages">;
};
export declare const useLocalRuntime: (chatModel: ChatModelAdapter, { cloud, ...options }?: LocalRuntimeOptions) => AssistantRuntime;