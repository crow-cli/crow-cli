import type { ThreadMessage } from "../types/message.js";
import type { ThreadSuggestion } from "../runtime/interfaces/thread-runtime-core.js";
export type SuggestionAdapterGenerateOptions = {
    messages: readonly ThreadMessage[];
    signal?: AbortSignal;
};
export type SuggestionAdapter = {
    generate: (options: SuggestionAdapterGenerateOptions) => Promise<readonly ThreadSuggestion[]> | AsyncGenerator<readonly ThreadSuggestion[], void>;
};
export declare const consumeSuggestionResult: (result: ReturnType<SuggestionAdapter["generate"]>, options: {
    signal: AbortSignal;
    onUpdate: (suggestions: readonly ThreadSuggestion[]) => void;
}) => Promise<void>;
export type CreateSuggestionAdapterOptions = {
    complete: (options: {
        prompt: string;
        signal?: AbortSignal;
    }) => Promise<readonly string[]>;
    count?: number | undefined;
    instructions?: string | undefined;
    maxMessages?: number | undefined;
};
export declare const createSuggestionAdapter: (options: CreateSuggestionAdapterOptions) => SuggestionAdapter;